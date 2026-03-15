# logic/logic_shunting_yard.py
# Port of ShuntingYard.cs
from __future__ import annotations
from collections import deque

from .logic_tokens import Token, TokenType


class LogicShuntingYardError(Exception):
    pass


class LogicShuntingYard:
    """
    Faithful port of ShuntingYard.cs
    """

    PRECEDENCE = {
        TokenType.AND: 2,
        TokenType.OR: 1,
    }

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens

    def to_rpn(self) -> list[Token]:
        output: list[Token] = []
        operators: deque[Token] = deque()

        for token in self.tokens:
            if token.type == TokenType.RULE:
                output.append(token)
                continue

            if token.type in (TokenType.AND, TokenType.OR):
                while (
                    operators
                    and operators[-1].type in self.PRECEDENCE
                    and self.PRECEDENCE[operators[-1].type]
                    >= self.PRECEDENCE[token.type]
                ):
                    output.append(operators.pop())
                operators.append(token)
                continue

            if token.type == TokenType.LEFT_PAREN:
                operators.append(token)
                continue

            if token.type == TokenType.RIGHT_PAREN:
                while operators and operators[-1].type != TokenType.LEFT_PAREN:
                    output.append(operators.pop())

                if not operators:
                    raise LogicShuntingYardError("Mismatched parentheses")

                operators.pop()  # Remove LEFT_PAREN
                continue

            raise LogicShuntingYardError(
                f"Unhandled token type: {token.type}"
            )

        while operators:
            op = operators.pop()
            if op.type in (TokenType.LEFT_PAREN, TokenType.RIGHT_PAREN):
                raise LogicShuntingYardError("Mismatched parentheses")
            output.append(op)

        return output
