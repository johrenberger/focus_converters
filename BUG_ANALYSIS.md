# Focus Converters — Bug Analysis Report

**Repository:** https://github.com/johrenberger/focus_converters  
**Branch:** `dev`  
**Date:** 2026-05-07  
**Analysis by:** Clawdexter (automated + manual review)

---

## Critical Bugs (Must Fix)

### BUG-001: Typo in Method Name `categorty` → `category`
**Severity:** HIGH  
**Files:**  
- `conversion_strategy.py` (17 instances)
- `converter.py` (7 call sites)
- **Every** Command class in conversion_strategy.py

**Description:**  
All Command classes have a method named `categorty` instead of `category`. This is a typo that works because Python doesn't enforce method name correctness, but it's:
- A violation of Python naming conventions (PEP 8)
- Confusing for developers
- Could hide the bug if any linter was looking for `category`

**Current (broken):**
```python
def categorty(self):
    return "column"  # or "datetime", "sql", etc.
```

**Expected:**
```python
def category(self):
    return "column"  # or "datetime", "sql", etc.
```

**Impact:** Code works today but will break if any tooling expects `category` method.

---

### BUG-002: Wrong Attribute Access in deferred_column_functions.py
**Severity:** HIGH  
**File:** `conversion_functions/deferred_column_functions.py`, line 70

**Description:**  
Typo: `conversion_arg.data_types` instead of `conversion_arg.data_type`

**Current (broken):**
```python
f"data_type: {conversion_arg.data_types} not implemented"
```

**Expected:**
```python
f"data_type: {conversion_arg.data_type} not implemented"
```

**Impact:** If this error path is hit, Python raises `AttributeError` instead of the intended `RuntimeError` with a clear message. Would mask the real error.

---

## Medium Severity

### BUG-003: SQLConditionConversionArgs Model Validation Issue
**Severity:** MEDIUM  
**File:** `configs/base_config.py`

**Description:**  
The validator expects `conditions` as a list and `default_value` without validation. If `conditions` is malformed or empty, the error message won't clearly indicate which field caused the validation failure.

**Current:**
```python
class SQLConditionConversionArgs(BaseModel):
    conditions: List[str]
    default_value: Any
```

**Recommendation:** Add validators:
```python
@field_validator("conditions")
@classmethod
def validate_conditions(cls, v):
    if not v:
        raise ValueError("conditions cannot be empty")
    return v
```

---

### BUG-004: Hardcoded Table Name in SQL Functions
**Severity:** MEDIUM  
**File:** `conversion_functions/sql_functions.py`

**Description:**  
`DEFAULT_SQL_TABLE_NAME = "cost_data"` is hardcoded. The TODO comment says this should be configurable. Currently any SQL query that uses a different table name will fail silently or produce wrong results.

**Impact:** Multi-tenant usage or queries expecting different table names won't work.

---

### BUG-005: No Graceful Handling of Unknown Aggregation Operations
**Severity:** MEDIUM  
**File:** `conversion_functions/column_functions.py`

**Description:**  
When `aggregation_operation` isn't recognized, `RuntimeError` is raised with no context about which column or plan triggered it.

**Current:**
```python
else:
    raise RuntimeError(
        f"Unknown aggregation_operation type: {conversion_args.aggregation_operation}"
    )
```

**Better:**
```python
else:
    raise RuntimeError(
        f"Unknown aggregation_operation type: {conversion_args.aggregation_operation} "
        f"for column: {plan.column}, plan: {plan.config_file_name}"
    )
```

---

## Low Severity / Code Quality

### BUG-006: TODOs Left in Production Code
**Severity:** LOW  
**Files:** Multiple

| File | Line | TODO |
|------|------|------|
| `validations.py` | 21 | "Find a robust local graph draw" |
| `sql_functions.py` | 12 | "Make it configurable" |
| `converter.py` | 41 | "Make this path configurable" |
| `base_config.py` | 115 | "Add option to allow query from multiple columns" |

**Recommendation:** Address or create GitHub issues for tracking.

---

### BUG-007: Mermaid API Call in Validation (Data Exfiltration Risk)
**Severity:** MEDIUM (Security)  
**File:** `conversion_functions/validations.py`

**Description:**  
The `mm()` function calls `https://mermaid.ink/img/` with the graph data base64-encoded. This sends internal graph structure to an external service.

**Current:**
```python
def mm(graph):
    graphbytes = graph.encode("ascii")
    base64_bytes = base64.b64encode(graphbytes)
    base64_string = base64_bytes.decode("ascii")
    return requests.get(f"https://mermaid.ink/img/{base64_string}").content
```

**Risk:** In enterprise environments, conversion graph structures (column names, mappings) could be considered sensitive. This also introduces an external dependency and potential data leak.

---

### BUG-008: Missing Error Handling in `__validate_column_names__`
**Severity:** LOW  
**File:** `conversion_functions/validations.py`

**Description:**  
When columns are missing, the error message lists them but doesn't indicate which plan depends on them. Makes debugging harder.

**Current:**
```python
columns_missing = sorted(set(source_columns) - set(lf.columns))
if columns_missing:
    raise ValueError(
        f"Column(s) '{', '.join(columns_missing)}' not found in data"
    )
```

**Better:** Include the plan name/config file that's missing the column.

---

## Security Observations

### SEC-001: Mermaid API Sends Data Externally
**Severity:** MEDIUM  
See BUG-007 above.

### SEC-002: No Input Sanitization on SQL Condition Templates  
**Severity:** MEDIUM  
**File:** `conversion_functions/sql_functions.py`

**Description:**  
SQL condition strings are rendered directly into Jinja templates without sanitization. While sqlglot validates the final query, a malicious input could potentially cause issues.

---

## Edge Cases Not Handled

### EDGE-001: Empty CSV Sections in IBM Cloud CSV Loader
**File:** `data_loaders/data_loader.py`

**Description:**  
The IBM Cloud CSV handling splits on `\n\n` and duplicates rows. If `sections` array is empty or has only one element, the loop logic may behave unexpectedly.

**Current:**
```python
sections = content.split("\n\n")
# If content is just "header\n\ndata\n", sections = ["header", "data"]
# Loop runs for i in range(0, 1) = [0], duplicating header rows
```

---

### EDGE-002: Parquet Dataset with Zero Row Groups
**File:** `data_loaders/data_loader.py`

**Description:**  
If `DEFAULT_BATCH_READ_SIZE = 50000` but the dataset has 0 row groups, tqdm will show 0% progress and the loop will yield nothing. Not an error, but potentially confusing.

---

### EDGE-003: Case Sensitivity in String Transform Steps
**File:** `conversion_functions/string_functions.py`

**Description:**  
The `step` comparison is case-sensitive. If someone passes `"Lower"` instead of `"lower"`, it raises `ValueError` with "Invalid step". Should be case-insensitive or have clearer error.

---

## Summary Table

| Bug ID | Severity | Category | File(s) | Fixable Without Context |
|--------|----------|----------|---------|------------------------|
| BUG-001 | HIGH | Typo | conversion_strategy.py | ✅ YES |
| BUG-002 | HIGH | Typo | deferred_column_functions.py | ✅ YES |
| BUG-003 | MEDIUM | Validation | configs/base_config.py | ✅ YES |
| BUG-004 | MEDIUM | Design | sql_functions.py | ✅ YES |
| BUG-005 | MEDIUM | Error Handling | column_functions.py | ✅ YES |
| BUG-006 | LOW | Tech Debt | Multiple | ⚠️ PARTIAL |
| BUG-007 | MEDIUM | Security | validations.py | ✅ YES |
| BUG-008 | LOW | Error Handling | validations.py | ✅ YES |
| SEC-001 | MEDIUM | Security | validations.py | ✅ YES |
| SEC-002 | MEDIUM | Security | sql_functions.py | ⚠️ NEEDS REVIEW |
| EDGE-001 | LOW | Edge Case | data_loader.py | ✅ YES |
| EDGE-002 | LOW | Edge Case | data_loader.py | ✅ YES |
| EDGE-003 | LOW | DX | string_functions.py | ✅ YES |

---

## Recommended Priority Fixes

1. **BUG-001** — Rename `categorty` → `category` across all files
2. **BUG-002** — Fix typo `data_types` → `data_type`
3. **BUG-007/SEC-001** — Make Mermaid graph generation optional or local-only
4. **BUG-005** — Improve error messages with context
5. **BUG-003** — Add validators to SQLConditionConversionArgs