# PR1 Tests — Learning Guide

## Why write tests?

Tests serve as:
- **Safety net** — When you change code later, tests tell you if something broke
- **Documentation** — Tests show exactly how each function is supposed to behave
- **Design feedback** — If a function is hard to test, it's probably poorly designed

---

## Test file structure

`tests/agents/test_pr1_initialize.py` — 36 tests organised into 7 test classes.

The file is at `tests/agents/test_pr1_initialize.py` because:
- `tests/` — top-level test directory (standard Python convention)
- `agents/` — mirrors `src/agents/` structure (tests are organised the same way as the source code)
- `test_pr1_initialize.py` — named after what it tests (PR1's initialize node)

---

## Test infrastructure

### Fixtures (shared test data)

```python
THREAD_ID = "test-thread-" + str(uuid.uuid4())
USER_ID = 42
```

These constants create a consistent test identity. A real UUID is used for the thread ID to catch any code that assumes a specific format.

### Helper: `_make_config`

```python
def _make_config(thread_id=THREAD_ID, user_id=USER_ID) -> dict:
    return {"configurable": {"thread_id": thread_id, "user_id": user_id}}
```

Simulates the `RunnableConfig` dictionary that LangGraph passes to every node. In production, the API layer sets `configurable.thread_id` and `configurable.user_id`.

### Helper: `_supabase_row`

```python
def _supabase_row(section_id: str, status: str = "pending") -> dict[str, Any]:
    return {
        "section_id": section_id,
        "status": status,
        "content": {"type": "doc", "content": []},
        "plain_text": "some text",
        "satisfaction_status": None,
    }
```

Simulates a row that would come back from `SupabaseClient.get_section_states()`. This is how we test the resume path without needing a real database.

### How mocking works

```python
with patch("agents.xbuddy.nodes.initialize.asyncio.to_thread", new=AsyncMock(return_value=[])):
    result = await initialize_node(state, _make_config())
```

`unittest.mock.patch` temporarily replaces `asyncio.to_thread` (the function that calls Supabase) with a fake that returns predefined data:
- `return_value=[]` → Simulates empty result → **cold start**
- `return_value=rows` → Simulates found data → **resume**
- `side_effect=Exception(...)` → Simulates crash → **fallback**

The patching is scoped to the `with` block — the real `asyncio.to_thread` is restored automatically after the test.

---

## Test class breakdown

### 1. `TestSectionID` — Testing the enums

**What it tests:** The enum values are correct and usable.

| Test | What it checks | Why it matters |
|---|---|---|
| `test_all_five_values_present` | All 5 SectionID values exist with correct strings | Missing a section breaks the graph |
| `test_section_order_matches_dependency_chain` | `SECTION_ORDER` list matches the correct sequence | The router relies on this order |
| `test_section_id_is_str_serialisable` | Enums compare equal to their string values | They need to match Supabase data |
| `test_router_directive_values` | STAY, NEXT, MODIFY are correct | These control graph navigation |
| `test_section_status_values` | PENDING, IN_PROGRESS, DONE are correct | These track section completion |

**Pattern:** Each enum value is explicitly asserted. If someone accidentally renames `PENDING = "pendente"`, the test catches it.

### 2. `TestProjectBuddyData` — Testing the data model

**What it tests:** ProjectBuddyData works correctly as a data container.

| Test | What it checks |
|---|---|
| `test_empty_construction` | All fields have correct default values (None for optionals, [] for lists) |
| `test_partial_population` | You can set some fields and leave others at defaults |
| `test_json_serialisable` | `model_dump()` produces a plain dict (for Supabase storage) |

**Key insight:** `ProjectBuddyData()` creates an instance with all fields at defaults. No required fields = easy to create anywhere in the code. This is intentional — fields are populated incrementally by `memory_updater`, not all at once.

### 3. `TestSectionState` — Testing section tracking

| Test | What it checks |
|---|---|
| `test_default_status_is_pending` | A new section starts as PENDING with no content |
| `test_with_content` | A completed section stores its content and status correctly |

### 4. `TestContextPacket` — Testing the context package

| Test | What it checks |
|---|---|
| `test_construction` | All fields can be set, optional fields (draft, validation_rules) are None by default |

### 5. `TestChatAgentOutput` — Testing the output model

| Test | What it checks |
|---|---|
| `test_valid_stay_directive` | `router_directive="stay"` is accepted |
| `test_valid_next_directive` | `router_directive="next"` is accepted |
| `test_valid_modify_directive` | `router_directive="modify:project_idea"` is accepted |
| `test_invalid_directive_raises` | `router_directive="jump"` raises a validation error |

**Why we validate:** The `router_directive` field controls which node runs next. An invalid value would crash the graph or cause infinite loops. The `@field_validator` catches these at creation time.

### 6. `TestXBuddyState` — Testing the main state

| Test | What it checks |
|---|---|
| `test_default_current_section_is_project_idea` | A new state starts at PROJECT_IDEA |

**Note:** XBuddyState extends `MessagesState` from LangGraph, which is a TypedDict-like class. We instantiate it as a dictionary with all required keys.

### 7. `TestHelpers` — Testing private helper functions

These test the 3 helper functions in `initialize.py`:

| Test | What it checks |
|---|---|
| `test_first_incomplete_all_pending` | When all are PENDING, returns PROJECT_IDEA |
| `test_first_incomplete_first_two_done` | When first 2 are DONE, returns ARCHITECTURE |
| `test_first_incomplete_all_done_returns_last` | When all are DONE, returns last section |
| `test_all_sections_done_false_when_pending` | Not done when one is pending |
| `test_all_sections_done_true` | Done only when all 5 are DONE |
| `test_build_section_state_valid_row` | Converting a valid Supabase row works |
| `test_build_section_state_unknown_section_id_raises` | Invalid section_id raises ValueError |
| `test_build_section_state_null_content` | Null content is handled gracefully |

**Why test private functions?** Because they contain the business logic that the public node depends on. Testing them directly means the node tests only need to check that the node calls them correctly.

### 8. `TestInitializeNodeColdStart` — Testing cold start

| Test | What it does |
|---|---|
| `test_cold_start_sets_project_idea` | Mocks empty Supabase result, verifies `current_section = PROJECT_IDEA` |
| `test_cold_start_initialises_all_sections_as_pending` | Checks all 5 sections exist with PENDING status |
| `test_cold_start_uses_config_thread_id` | Verifies the thread_id from config is used |
| `test_cold_start_generates_thread_id_when_missing` | When no thread_id provided, a valid UUID is generated |
| `test_cold_start_error_count_reset` | Previous error count is cleared |

**Mock pattern used everywhere:**
```python
with patch("agents.xbuddy.nodes.initialize.asyncio.to_thread",
           new=AsyncMock(return_value=[])):
    result = await initialize_node(state, _make_config())
```

### 9. `TestInitializeNodeResume` — Testing resume

| Test | What it does |
|---|---|
| `test_resume_restores_section_states` | Returns persisted rows → states are rebuilt |
| `test_resume_sets_current_section_to_first_incomplete` | 2 done, 1 in-progress → current = ARCHITECTURE |
| `test_resume_finished_true_when_all_done` | All 5 done → `finished = True` |

### 10. `TestInitializeNodeEdgeCases` — Testing failure modes

| Test | What it simulates |
|---|---|
| `test_supabase_unavailable_falls_back_to_cold_start` | Supabase throws exception → cold start |
| `test_all_corrupted_rows_falls_back_to_cold_start` | All rows have invalid section_id → cold start |
| `test_partial_corruption_skips_bad_rows` | 1 valid + 1 invalid → valid kept, invalid skipped |
| `test_none_config_handled` | `config=None` → uses state's thread_id |

---

## Running the tests

```bash
# Run just PR1 tests
uv run pytest tests/agents/test_pr1_initialize.py -v

# Run a specific test class
uv run pytest tests/agents/test_pr1_initialize.py::TestInitializeNodeColdStart -v

# Run a specific test
uv run pytest tests/agents/test_pr1_initialize.py::TestHelpers::test_first_incomplete_all_pending -v

# Run all tests in the project
uv run pytest -v
```

## Understanding test output

```
tests/agents/test_pr1_initialize.py::TestSectionID::test_all_five_values_present PASSED  [  2%]
```

- `tests/agents/test_pr1_initialize.py` — the file
- `TestSectionID` — the test class
- `test_all_five_values_present` — the specific test function
- `PASSED` — it passed
- `[2%]` — progress through the test suite

A failure looks like:
```
FAILED test_pr1_initialize.py::TestSectionID::test_section_id_is_str_serialisable
AssertionError: assert 'SectionID.PROJECT_IDEA' == 'project_idea'
```

This tells you the exact line that failed and what was expected vs what was received.

---

## Summary: What's covered and what's not

**Covered by these tests:**
- ✅ All enum values are correct
- ✅ All models can be constructed with correct defaults
- ✅ Validator catches invalid router directives
- ✅ Cold start sets correct initial state
- ✅ Resume restores from persisted data
- ✅ Resume finds the right section when some are done
- ✅ All-done state sets finished=True
- ✅ Supabase crash doesn't crash the node
- ✅ Corrupted data is handled gracefully
- ✅ Missing thread_id generates one
- ✅ None config doesn't crash

**Not covered (deliberately):**
- ❌ Router logic (tested in PR2)
- ❌ LLM calls (tested in PR3)
- ❌ Actual Supabase connection (integration test, not unit test)
- ❌ Full graph flow (e2e test, done separately)
