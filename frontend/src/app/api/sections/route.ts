import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const logApiCall = (phase: string, data: Record<string, unknown>, level: 'INFO' | 'WARN' | 'ERROR' = 'INFO') => {
  const timestamp = new Date().toISOString();
  const logLevel = process.env.NODE_ENV === 'development' ? 'DEBUG' : 'INFO';
  
  if (process.env.NODE_ENV === 'production' && level === 'INFO' && process.env.ENABLE_DEBUG_LOGS !== 'true') {
    return;
  }
  
  const logPrefix = level === 'ERROR' ? '🔴' : level === 'WARN' ? '🟡' : '🔵';
  console.log(`\n${logPrefix} === SECTIONS API [${level}] [${phase}] - ${timestamp} ===`);
  console.log(JSON.stringify(data, null, 2));
  console.log('=====================================\n');
};

// DentApp API configuration
const getDentAppApiUrl = () => {
  return process.env.DENTAPP_API_URL || 'https://gsd.keypersonofinfluence.com';
};

const getDentAppHeaders = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  
  const bearerToken = process.env.DENTAPP_API_BEARER_TOKEN;
  if (bearerToken) {
    headers['Authorization'] = `Bearer ${bearerToken}`;
  }
  
  return headers;
};

// Backend API configuration
const getBackendApiUrl = () => {
  const isLocal = process.env.NEXT_PUBLIC_API_ENV === 'local';
  return isLocal 
    ? process.env.VALUE_CANVAS_API_URL_LOCAL 
    : process.env.VALUE_CANVAS_API_URL_PRODUCTION;
};

const getBackendHeaders = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  
  const token = process.env.VALUE_CANVAS_API_TOKEN;
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  return headers;
};

// Agent ID mapping
const AGENT_ID_MAP: Record<string, number> = {
  'xbuddy': 1, // XBuddy agent ID
};

// Supabase client initialization
const getSupabaseClient = () => {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  
  if (!supabaseUrl || !supabaseAnonKey) {
    return null;
  }
  
  return createClient(supabaseUrl, supabaseAnonKey);
};

// XBuddy section mapping (string ID to display info)
const XBUDDY_SECTIONS: Record<string, { name: string; displayName: string }> = {
  'project_idea': { name: 'Project Idea', displayName: 'Project Idea & Goals' },
  'requirements': { name: 'Requirements', displayName: 'Requirements Gathering' },
  'architecture': { name: 'Architecture', displayName: 'Architecture Design' },
  'tech_stack': { name: 'Tech Stack', displayName: 'Technology Selection' },
  'implementation': { name: 'Implementation', displayName: 'Implementation Planning' },
};

export async function POST(req: NextRequest) {
  const requestStartTime = Date.now();
  
  try {
    const body = await req.json();
    const { action, userId, sectionId, threadId, content, refinementPrompt } = body;
    
    logApiCall('REQUEST_START', {
      action,
      userId,
      sectionId,
      threadId,
      hasContent: !!content,
      hasRefinementPrompt: !!refinementPrompt,
    });
    
    // Validate userId
    if (!userId || !Number.isInteger(Number(userId)) || Number(userId) <= 0) {
      return NextResponse.json(
        { success: false, message: 'Invalid userId' },
        { status: 400 }
      );
    }
    
    const finalUserId = Number(userId);
    
    // Handle different actions
    switch (action) {
      case 'get-all-sections': {
        // Get all sections from Supabase
        const supabase = getSupabaseClient();
        
        if (!supabase) {
          logApiCall('SUPABASE_ERROR', {
            message: 'Supabase not configured',
          }, 'ERROR');
          return NextResponse.json({
            success: true,
            data: { sections: [] },
          });
        }
        
        // If threadId is provided, get sections for that thread
        // Otherwise, get all sections for the user (across all threads)
        let query = supabase
          .from('section_states')
          .select('*')
          .eq('user_id', finalUserId)
          .eq('agent_id', 'project-buddy');
        
        if (threadId) {
          query = query.eq('thread_id', threadId);
        }
        
        logApiCall('SUPABASE_REQUEST', {
          userId: finalUserId,
          threadId: threadId || 'all',
        });
        
        const { data: sectionStates, error } = await query.order('created_at', { ascending: true });
        
        if (error) {
          logApiCall('SUPABASE_ERROR', {
            error: error.message,
          }, 'ERROR');
          return NextResponse.json({
            success: true,
            data: { sections: [] },
          });
        }
        
        // Transform Supabase data to expected format
        // If threadId is provided, return sections for that thread
        // Otherwise, return unique sections across all threads (latest version)
        const sectionsMap = new Map<string, any>();
        
        if (sectionStates && sectionStates.length > 0) {
          for (const state of sectionStates) {
            const sectionId = state.section_id;
            const sectionInfo = XBUDDY_SECTIONS[sectionId];
            
            if (sectionInfo) {
              // Use section_id as key, keep latest version if multiple threads
              const key = threadId ? `${threadId}:${sectionId}` : sectionId;
              
              if (!sectionsMap.has(sectionId) || (threadId && key.includes(threadId))) {
                const hasContent = !!(state.content && (
                  (typeof state.content === 'object' && Object.keys(state.content).length > 0) ||
                  (typeof state.content === 'string' && state.content.length > 0)
                ));
                
                sectionsMap.set(sectionId, {
                  section_id: sectionId, // Keep as string for xbuddy
                  section_name: sectionInfo.name,
                  name: sectionInfo.displayName,
                  is_completed: state.status === 'done',
                  has_content: hasContent,
                  current_version: 1, // Default version
                  ai_interaction_count: 0, // Not tracked in current schema
                  status: state.status || 'pending',
                  created_at: state.created_at,
                  updated_at: state.updated_at,
                });
              }
            }
          }
        }
        
        // If no sections found in DB, return all possible sections with pending status
        if (sectionsMap.size === 0) {
          for (const [sectionId, sectionInfo] of Object.entries(XBUDDY_SECTIONS)) {
            sectionsMap.set(sectionId, {
              section_id: sectionId,
              section_name: sectionInfo.name,
              name: sectionInfo.displayName,
              is_completed: false,
              has_content: false,
              current_version: 1,
              ai_interaction_count: 0,
              status: 'pending',
            });
          }
        }
        
        const sections = Array.from(sectionsMap.values());
        
        logApiCall('SUPABASE_SUCCESS', {
          sectionCount: sections.length,
          sections: sections.map(s => ({ id: s.section_id, name: s.name, status: s.status })),
        });
        
        return NextResponse.json({
          success: true,
          data: { sections },
        });
      }
      
      case 'get-section-content': {
        if (!sectionId) {
          return NextResponse.json(
            { success: false, message: 'sectionId is required' },
            { status: 400 }
          );
        }
        
        if (!threadId) {
          return NextResponse.json(
            { success: false, message: 'threadId is required to get section content' },
            { status: 400 }
          );
        }
        
        // Get section content from Supabase
        const supabase = getSupabaseClient();
        
        if (!supabase) {
          logApiCall('SUPABASE_ERROR', {
            message: 'Supabase not configured',
          }, 'ERROR');
          return NextResponse.json({
            success: false,
            message: 'Supabase not configured',
          }, { status: 500 });
        }
        
        logApiCall('SUPABASE_REQUEST', {
          userId: finalUserId,
          threadId: threadId,
          sectionId: sectionId,
        });
        
        console.log('[API] Fetching section content:', {
          userId: finalUserId,
          threadId: threadId,
          sectionId: sectionId,
          agentId: 'project-buddy'
        });
        
        const { data: sectionState, error } = await supabase
          .from('section_states')
          .select('*')
          .eq('user_id', finalUserId)
          .eq('thread_id', threadId)
          .eq('agent_id', 'project-buddy')
          .eq('section_id', sectionId)
          .maybeSingle();
        
        console.log('[API] Supabase query result:', {
          hasData: !!sectionState,
          hasError: !!error,
          error: error?.message,
          sectionStateKeys: sectionState ? Object.keys(sectionState) : null,
          contentType: sectionState?.content ? typeof sectionState.content : null
        });
        
        if (error) {
          logApiCall('SUPABASE_ERROR', {
            error: error.message,
            code: error.code,
            details: error.details,
          }, 'ERROR');
          return NextResponse.json({
            success: false,
            message: error.message || 'Database query failed',
          }, { status: 500 });
        }
        
        if (!sectionState) {
          logApiCall('SUPABASE_SUCCESS', {
            hasContent: false,
            message: 'Section not found',
          });
          console.log('[API] Section not found in database');
          return NextResponse.json({
            success: true,
            data: null,
          });
        }
        
        // Transform Supabase data to expected format
        const content = sectionState.content;
        let contentText = '';
        
        if (content) {
          if (typeof content === 'string') {
            contentText = content;
          } else if (typeof content === 'object') {
            // Tiptap JSON format - extract plain text
            if (content.plain_text) {
              contentText = content.plain_text;
            } else if (content.text) {
              contentText = content.text;
            } else {
              // Try to extract text from Tiptap document structure
              const extractText = (node: any): string => {
                if (typeof node === 'string') return node;
                if (node?.text) return node.text;
                if (node?.content && Array.isArray(node.content)) {
                  return node.content.map(extractText).join('');
                }
                return '';
              };
              contentText = extractText(content);
            }
          }
        }
        
        const result = {
          content: {
            text: contentText,
          },
          is_completed: sectionState.status === 'done',
          current_version: 1,
          created_at: sectionState.created_at,
          updated_at: sectionState.updated_at,
        };
        
        logApiCall('SUPABASE_SUCCESS', {
          hasContent: !!contentText,
          contentLength: contentText.length,
        });
        
        return NextResponse.json({
          success: true,
          data: result,
        });
      }
      
      case 'refine-section': {
        if (!sectionId || !threadId || !refinementPrompt) {
          return NextResponse.json(
            { success: false, message: 'sectionId, threadId, and refinementPrompt are required' },
            { status: 400 }
          );
        }
        
        const agentId = 'xbuddy'; // Currently only xbuddy is supported
        const backendUrl = getBackendApiUrl();
        
        if (!backendUrl) {
          return NextResponse.json(
            { success: false, message: 'Backend API URL not configured' },
            { status: 500 }
          );
        }
        
        const refineUrl = `${backendUrl}/refine_section/${agentId}/${sectionId}`;
        
        logApiCall('BACKEND_REQUEST', {
          url: refineUrl,
          method: 'POST',
          payload: {
            user_id: finalUserId,
            thread_id: threadId,
            refinement_prompt: refinementPrompt,
          },
        });
        
        const response = await fetch(refineUrl, {
          method: 'POST',
          headers: getBackendHeaders(),
          body: JSON.stringify({
            user_id: finalUserId,
            thread_id: threadId,
            refinement_prompt: refinementPrompt,
          }),
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          logApiCall('BACKEND_ERROR', {
            status: response.status,
            error: errorText,
          }, 'ERROR');
          throw new Error(`Backend API error: ${response.status}`);
        }
        
        const data = await response.json();
        logApiCall('BACKEND_SUCCESS', {
          hasRefinedContent: !!data.refined_content,
        });
        
        return NextResponse.json({
          success: true,
          data: data,
        });
      }
      
      case 'update-section-content': {
        if (!sectionId || !content) {
          return NextResponse.json(
            { success: false, message: 'sectionId and content are required' },
            { status: 400 }
          );
        }
        
        const agentId = AGENT_ID_MAP['xbuddy'] || 1;
        const dentAppUrl = `${getDentAppApiUrl()}/section_states/${agentId}/${sectionId}`;
        
        // Content from refine is already plain text, but handle both formats
        let plainTextContent: string;
        if (typeof content === 'string') {
          plainTextContent = content;
        } else if (typeof content === 'object' && content.type === 'doc') {
          // Tiptap format - extract plain text
          const extractText = (node: any): string => {
            if (node.type === 'text') {
              return node.text || '';
            }
            if (node.content && Array.isArray(node.content)) {
              return node.content.map(extractText).join('');
            }
            return '';
          };
          plainTextContent = extractText(content);
        } else {
          plainTextContent = String(content);
        }
        
        logApiCall('DENTAPP_REQUEST', {
          url: dentAppUrl,
          method: 'POST',
          payload: {
            user_id: finalUserId,
            content: plainTextContent.substring(0, 100) + '...',
            contentLength: plainTextContent.length,
          },
        });
        
        const response = await fetch(dentAppUrl, {
          method: 'POST',
          headers: getDentAppHeaders(),
          body: JSON.stringify({
            user_id: finalUserId,
            content: plainTextContent,
          }),
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          logApiCall('DENTAPP_ERROR', {
            status: response.status,
            error: errorText,
          }, 'ERROR');
          throw new Error(`DentApp API error: ${response.status}`);
        }
        
        const data = await response.json();
        logApiCall('DENTAPP_SUCCESS', {
          success: data.success,
        });
        
        return NextResponse.json({
          success: true,
          data: data,
        });
      }
      
      case 'sync-section': {
        if (!sectionId || !threadId) {
          return NextResponse.json(
            { success: false, message: 'sectionId and threadId are required' },
            { status: 400 }
          );
        }
        
        const agentId = 'xbuddy'; // Currently only xbuddy is supported
        const backendUrl = getBackendApiUrl();
        
        if (!backendUrl) {
          return NextResponse.json(
            { success: false, message: 'Backend API URL not configured' },
            { status: 500 }
          );
        }
        
        const syncUrl = `${backendUrl}/sync_section/${agentId}/${sectionId}?user_id=${finalUserId}&thread_id=${threadId}`;
        
        logApiCall('BACKEND_REQUEST', {
          url: syncUrl,
          method: 'POST',
        });
        
        const response = await fetch(syncUrl, {
          method: 'POST',
          headers: getBackendHeaders(),
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          logApiCall('BACKEND_ERROR', {
            status: response.status,
            error: errorText,
          }, 'ERROR');
          
          // Return more detailed error information
          try {
            const errorJson = JSON.parse(errorText);
            return NextResponse.json(
              { success: false, message: errorJson.detail || 'Sync failed' },
              { status: response.status }
            );
          } catch {
            return NextResponse.json(
              { success: false, message: errorText || 'Sync failed' },
              { status: response.status }
            );
          }
        }
        
        const data = await response.json();
        logApiCall('BACKEND_SUCCESS', {
          success: data.success,
          extractedFields: data.extracted_fields,
        });
        
        return NextResponse.json({
          success: true,
          data: data,
        });
      }
      
      default:
        return NextResponse.json(
          { success: false, message: `Unknown action: ${action}` },
          { status: 400 }
        );
    }
    
  } catch (error) {
    const errorResponseTime = Date.now() - requestStartTime;
    
    logApiCall('REQUEST_ERROR', {
      error: error instanceof Error ? error.message : 'Unknown error',
      stack: error instanceof Error ? error.stack : undefined,
      responseTime: `${errorResponseTime}ms`,
    }, 'ERROR');
    
    return NextResponse.json(
      {
        success: false,
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

