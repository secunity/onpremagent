import parsy

TCP_FLAGS = {
    "fin": 0b00000001,
    "syn": 0b00000010,
    "rst": 0b00000100,
    "psh": 0b00001000,
    "ack": 0b00010000,
    "urg": 0b00100000,
    "ece": 0b01000000,
    "cwr": 0b10000000,
}


def _lexeme(p: parsy.Parser) -> parsy.Parser:
    return p << parsy.whitespace.optional()


_flag = _lexeme(
    parsy.alt(*(parsy.string(name).result(bit) for name, bit in TCP_FLAGS.items()))
)

_lparen = _lexeme(parsy.string("("))
_rparen = _lexeme(parsy.string(")"))
_not = _lexeme(parsy.string("!"))
_and = _lexeme(parsy.string("&"))
_or = _lexeme(parsy.string("|"))


@parsy.generate
def _atom():
    yield _lparen
    result = yield _expr
    yield _rparen
    return result


_atom = _atom | _flag


@parsy.generate
def _unary():
    nots = yield _not.many()
    val = yield _atom
    for _ in nots:
        val = (~val) & 0xFF
    return val


@parsy.generate
def _and_expr():
    first = yield _unary
    rest = yield (_and >> _unary).many()
    result = first
    for val in rest:
        result &= val
    return result


@parsy.generate
def _expr():
    first = yield _and_expr
    rest = yield (_or >> _and_expr).many()
    result = first
    for val in rest:
        result |= val
    return result


tcp_flags_parser = parsy.whitespace.optional() >> _expr
