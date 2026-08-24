"""A deliberately small arithmetic evaluator with no Python execution surface."""

from __future__ import annotations

import ast
import operator
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel


class CalculationResult(BaseModel):
    expression: str
    value: Decimal


class CalculationService:
    """Evaluate bounded arithmetic using an allowlisted AST."""

    _binary = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def calculate(self, expression: str) -> CalculationResult:
        normalized = expression.strip()
        if not normalized or len(normalized) > 200:
            raise ValueError("expression must contain at most 200 characters")
        try:
            tree = ast.parse(normalized, mode="eval")
            value = self._evaluate(tree.body)
        except (SyntaxError, InvalidOperation, ArithmeticError, OverflowError) as error:
            raise ValueError("unsupported or invalid arithmetic expression") from error
        if not value.is_finite():
            raise ValueError("unsupported non-finite arithmetic result")
        return CalculationResult(expression=normalized, value=value.normalize())

    def _evaluate(self, node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary:
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > Decimal("1e6")):
                raise ValueError("unsupported exponent")
            return self._binary[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary:
            return self._unary[type(node.op)](self._evaluate(node.operand))
        raise ValueError("unsupported arithmetic syntax")
