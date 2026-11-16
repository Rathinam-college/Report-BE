"""
Safe Mathematical Formula Engine for Category Management.
Evaluates formulas using safe Shunting-Yard tokenization and AST-like evaluation.
Guaranteed safe: NEVER uses eval(), exec(), or arbitrary code execution.
Includes cycle detection, zero-division protection, and category ID reference mapping.
"""
import re
from typing import Dict, List, Any, Optional, Tuple, Set

class FormulaError(Exception):
    pass

class DivisionByZeroError(FormulaError):
    pass

class CircularDependencyError(FormulaError):
    pass

class MissingCategoryError(FormulaError):
    pass

class InvalidSyntaxError(FormulaError):
    pass


def normalize_expression(expr: str, available_categories: List[Dict[str, Any]]) -> Tuple[str, str, List[int], List[str]]:
    """
    Normalizes an expression string:
    - Normalizes multiplication ('x', 'X', '×' -> '*') and division ('÷', ':' -> '/')
    - Auto-wraps bare category names into [Category Name]
    - Maps category names to category IDs -> produces id_expression: e.g. ([CAT_ID:1] + [CAT_ID:2]) * 0.18
    - Returns (normalized_expr, id_expr, category_ids, category_names)
    """
    if not expr or not expr.strip():
        raise InvalidSyntaxError("Formula expression cannot be empty")

    res = expr.strip()
    res = re.sub(r'[×]', '*', res)
    res = re.sub(r'[÷:]', '/', res)
    res = re.sub(r'[−–]', '-', res)
    res = res.replace(',', '')

    # Replace standalone 'x' or 'X' surrounded by whitespace or numbers with '*'
    res = re.sub(r'(\s|\d|\)|\])[xX](\s|\d|\(|\[)', r'\1*\2', res)

    # Sort categories by name length descending so longer category names match first
    sorted_cats = sorted(available_categories, key=lambda c: len(c.get("name", "")), reverse=True)

    # 1. First auto-wrap bare category names that are not enclosed in brackets
    for cat in sorted_cats:
        c_name = cat.get("name", "").strip()
        if not c_name:
            continue
        escaped = re.escape(c_name)
        # Match c_name when not preceded by '[' and not followed by ']'
        pattern = r'(?<!\[)' + escaped + r'(?!\])'
        res = re.sub(pattern, f'[{c_name}]', res, flags=re.IGNORECASE)

        c_code = cat.get("code", "").strip() if cat.get("code") else ""
        if c_code:
            escaped_code = re.escape(c_code)
            pattern_code = r'(?<!\[)' + escaped_code + r'(?!\])'
            res = re.sub(pattern_code, f'[{c_name}]', res, flags=re.IGNORECASE)

    # 2. Extract referenced category names and map to IDs
    category_ids = []
    category_names = []
    id_expr = res

    # Map available categories by name (case-insensitive) and by ID
    cat_by_name = {c.get("name", "").strip().lower(): c for c in available_categories if c.get("name")}
    cat_by_id = {c.get("id"): c for c in available_categories if c.get("id") is not None}

    # Find all [ ... ] tokens
    bracket_matches = re.findall(r'\[(.*?)\]', res)
    for token in bracket_matches:
        t_clean = token.strip()
        t_lower = t_clean.lower()

        # Check if already [CAT_ID:123]
        cat_id_match = re.match(r'^CAT_ID:(\d+)$', t_clean, re.IGNORECASE)
        if cat_id_match:
            cid = int(cat_id_match.group(1))
            if cid in cat_by_id:
                if cid not in category_ids:
                    category_ids.append(cid)
                    category_names.append(cat_by_id[cid].get("name", f"Category {cid}"))
            continue

        matched_cat = cat_by_name.get(t_lower)
        if matched_cat:
            cid = matched_cat.get("id")
            cname = matched_cat.get("name")
            if cid is not None and cid not in category_ids:
                category_ids.append(cid)
                category_names.append(cname)
            # Replace token with [CAT_ID:id] in id_expr
            escaped_token = re.escape(f"[{token}]")
            id_expr = re.sub(escaped_token, f"[CAT_ID:{cid}]", id_expr)

    return res, id_expr, category_ids, category_names


def tokenize(expression: str) -> List[Tuple[str, Any]]:
    """
    Tokenizes a formula expression safely.
    Returns a list of (token_type, value) tuples:
    types: 'NUMBER', 'CATEGORY_ID', 'CATEGORY_NAME', 'OP', 'LPAREN', 'RPAREN'
    """
    tokens = []
    i = 0
    length = len(expression)

    while i < length:
        ch = expression[i]

        # Skip whitespace
        if ch.isspace():
            i += 1
            continue

        # Brackets [Category Name] or [CAT_ID:123]
        if ch == '[':
            close_idx = expression.find(']', i)
            if close_idx == -1:
                raise InvalidSyntaxError("Missing closing bracket ']' in formula")
            content = expression[i+1:close_idx].strip()
            cat_id_match = re.match(r'^CAT_ID:(\d+)$', content, re.IGNORECASE)
            if cat_id_match:
                tokens.append(('CATEGORY_ID', int(cat_id_match.group(1))))
            else:
                tokens.append(('CATEGORY_NAME', content))
            i = close_idx + 1
            continue

        # Numbers (including decimals)
        if ch.isdigit() or (ch == '.' and i + 1 < length and expression[i+1].isdigit()):
            num_str = ch
            i += 1
            has_dot = (ch == '.')
            while i < length and (expression[i].isdigit() or (expression[i] == '.' and not has_dot)):
                if expression[i] == '.':
                    has_dot = True
                num_str += expression[i]
                i += 1
            # Check for trailing % (e.g. 18% -> 0.18)
            if i < length and expression[i] == '%':
                val = float(num_str) / 100.0
                tokens.append(('NUMBER', val))
                i += 1
            else:
                tokens.append(('NUMBER', float(num_str)))
            continue

        # Parentheses
        if ch == '(':
            tokens.append(('LPAREN', '('))
            i += 1
            continue
        if ch == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
            continue

        # Operators
        if ch in ('+', '-', '*', '/', '%'):
            # Detect unary minus
            # Unary if at start of expression, or immediately after an operator or '('
            if ch == '-':
                prev_is_op = (not tokens) or (tokens[-1][0] in ('OP', 'LPAREN'))
                if prev_is_op:
                    tokens.append(('OP', 'UNARY_MINUS'))
                    i += 1
                    continue
            tokens.append(('OP', ch))
            i += 1
            continue

        raise InvalidSyntaxError(f"Unexpected character '{ch}' in formula expression")

    return tokens


def to_rpn(tokens: List[Tuple[str, Any]]) -> List[Tuple[str, Any]]:
    """
    Converts tokens to Reverse Polish Notation (RPN) using Dijkstra's Shunting-Yard algorithm.
    """
    precedence = {
        'UNARY_MINUS': 3,
        '*': 2,
        '/': 2,
        '%': 2,
        '+': 1,
        '-': 1
    }
    right_associative = {'UNARY_MINUS'}

    output_queue = []
    operator_stack = []

    for t_type, val in tokens:
        if t_type in ('NUMBER', 'CATEGORY_ID', 'CATEGORY_NAME'):
            output_queue.append((t_type, val))
        elif t_type == 'OP':
            while operator_stack and operator_stack[-1][0] == 'OP':
                top_op = operator_stack[-1][1]
                p_curr = precedence.get(val, 0)
                p_top = precedence.get(top_op, 0)
                if (val not in right_associative and p_curr <= p_top) or (val in right_associative and p_curr < p_top):
                    output_queue.append(operator_stack.pop())
                else:
                    break
            operator_stack.append((t_type, val))
        elif t_type == 'LPAREN':
            operator_stack.append((t_type, val))
        elif t_type == 'RPAREN':
            found_lparen = False
            while operator_stack:
                op = operator_stack.pop()
                if op[0] == 'LPAREN':
                    found_lparen = True
                    break
                output_queue.append(op)
            if not found_lparen:
                raise InvalidSyntaxError("Mismatched parentheses: extra closing ')'")

    while operator_stack:
        op = operator_stack.pop()
        if op[0] in ('LPAREN', 'RPAREN'):
            raise InvalidSyntaxError("Mismatched parentheses: unclosed '(' in formula")
        output_queue.append(op)

    return output_queue


def evaluate_rpn(rpn_tokens: List[Tuple[str, Any]], category_values: Dict[Any, float]) -> float:
    """
    Evaluates an RPN token list using a safe stack.
    category_values can be keyed by category_id (int) or category_name (str lower).
    """
    stack = []

    for t_type, val in rpn_tokens:
        if t_type == 'NUMBER':
            stack.append(float(val))
        elif t_type == 'CATEGORY_ID':
            # Lookup by ID
            amt = category_values.get(val)
            if amt is None:
                # Try string key
                amt = category_values.get(str(val), 0.0)
            stack.append(float(amt if amt is not None else 0.0))
        elif t_type == 'CATEGORY_NAME':
            # Lookup by lower-cased name
            name_lower = str(val).strip().lower()
            amt = category_values.get(name_lower)
            if amt is None:
                amt = category_values.get(val, 0.0)
            stack.append(float(amt if amt is not None else 0.0))
        elif t_type == 'OP':
            if val == 'UNARY_MINUS':
                if not stack:
                    raise InvalidSyntaxError("Syntax error: invalid unary minus position")
                a = stack.pop()
                stack.append(-a)
            else:
                if len(stack) < 2:
                    raise InvalidSyntaxError(f"Syntax error: insufficient operands for operator '{val}'")
                b = stack.pop()
                a = stack.pop()
                if val == '+':
                    stack.append(a + b)
                elif val == '-':
                    stack.append(a - b)
                elif val == '*':
                    stack.append(a * b)
                elif val == '/':
                    if b == 0.0:
                        # Division by zero: return 0.0 safely
                        stack.append(0.0)
                    else:
                        stack.append(a / b)
                elif val == '%':
                    # Percentage or modulo
                    if b == 0.0:
                        stack.append(0.0)
                    else:
                        stack.append((a / b) * 100.0)

    if not stack:
        return 0.0
    if len(stack) > 1:
        raise InvalidSyntaxError("Syntax error: formula expression has too many values without operators")

    res = stack.pop()
    return round(res, 2)


def evaluate_formula(expression_or_def: Any, category_values: Dict[Any, float]) -> float:
    """
    Unified entry point to evaluate a formula safely.
    Can take raw expression string or formula_definition dict.
    """
    if not expression_or_def:
        return 0.0

    expr = ""
    if isinstance(expression_or_def, dict):
        expr = expression_or_def.get("id_expression") or expression_or_def.get("expression", "")
    elif isinstance(expression_or_def, str):
        expr = expression_or_def

    if not expr.strip():
        return 0.0

    tokens = tokenize(expr)
    rpn = to_rpn(tokens)
    return evaluate_rpn(rpn, category_values)


def detect_circular_dependencies(
    all_categories: List[Dict[str, Any]], 
    new_cat_id: Optional[int], 
    new_dependencies: List[int]
) -> Tuple[bool, Optional[str]]:
    """
    Checks if adding/updating a category creates a circular dependency.
    Uses DFS on the directed dependency graph.
    Returns (has_cycle, error_message).
    """
    # Build graph: cat_id -> set of dependency cat_ids
    graph: Dict[int, Set[int]] = {}

    for cat in all_categories:
        cid = cat.get("id")
        if cid is None:
            continue
        c_type = cat.get("category_type", "DIRECT")
        f_def = cat.get("formula_definition") or {}
        deps = set()
        if c_type == "FORMULA" and isinstance(f_def, dict):
            dep_ids = f_def.get("category_ids") or []
            deps = set(dep_ids)
        graph[cid] = deps

    # Overlay candidate category
    target_id = new_cat_id or -999  # Temporary ID if creating new category
    graph[target_id] = set(new_dependencies)

    # Self-reference check
    if target_id in graph[target_id]:
        return True, "Formula cannot reference the category itself"

    # DFS cycle detection
    visited = set()
    rec_stack = set()
    cycle_path = []

    def dfs(node: int, path: List[int]) -> bool:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                if dfs(neighbor, path):
                    return True
            elif neighbor in rec_stack:
                # Cycle found
                cycle_start_idx = path.index(neighbor)
                cycle_path.extend(path[cycle_start_idx:] + [neighbor])
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    for node in list(graph.keys()):
        if node not in visited:
            if dfs(node, []):
                # Map IDs to names for human-readable error message
                cat_name_map = {c.get("id"): c.get("name") for c in all_categories if c.get("id")}
                cat_name_map[target_id] = "New Category"
                cycle_names = [cat_name_map.get(i, f"Category #{i}") for i in cycle_path]
                return True, f"Circular Dependency detected: {' → '.join(cycle_names)}"

    return False, None
