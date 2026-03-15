# logic/logic_tokens.py
# Port of Tokeniser.cs
from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass


class TokenType(Enum):
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    AND = auto()
    OR = auto()
    RULE = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str | None = None


class LogicTokeniserError(Exception):
    pass


class LogicTokeniser:
    """
    Faithful port of Tokeniser.cs
    """

    def __init__(self, logic: str):
        self.logic = logic
        self.index = 0
        self.length = len(logic)

    def tokenise(self) -> list[Token]:
        tokens: list[Token] = []

        while self._has_more():
            c = self._peek()

            if c.isspace():
                self._consume()
                continue

            if c == "(":
                tokens.append(Token(TokenType.LEFT_PAREN))
                self._consume()
                continue

            if c == ")":
                tokens.append(Token(TokenType.RIGHT_PAREN))
                self._consume()
                continue

            if c.isalpha():
                identifier = self._read_identifier()

                if identifier.lower() == "and":
                    tokens.append(Token(TokenType.AND))
                    continue

                if identifier.lower() == "or":
                    tokens.append(Token(TokenType.OR))
                    continue

                # Otherwise, must be a logic rule
                rule_token = self._read_rule(identifier)
                tokens.append(rule_token)
                continue

            raise LogicTokeniserError(
                f"Unexpected character '{c}' at position {self.index}"
            )

        return tokens

    # ---------- Internal helpers ----------

    def _has_more(self) -> bool:
        return self.index < self.length

    def _peek(self) -> str:
        return self.logic[self.index]

    def _consume(self) -> None:
        self.index += 1

    def _read_identifier(self) -> str:
        start = self.index
        while self._has_more() and self._peek().isalpha():
            self._consume()
        return self.logic[start:self.index]

    def _read_rule(self, name: str) -> Token:
        # Bare rule with no arguments (e.g. CanWarp)
        if not self._has_more() or self._peek() != "(":
            return Token(TokenType.RULE, name)

        self._consume()  # '('

        value_start = self.index
        depth = 1

        while self._has_more():
            c = self._peek()

            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break

            self._consume()

        if depth != 0:
            raise LogicTokeniserError(
                f"Unclosed '(' in rule '{name}'"
            )

        value = self.logic[value_start:self.index].strip()
        self._consume()  # ')'

        return Token(TokenType.RULE, f"{name}({value})")