from multichannel_gateway.core.name_generator import (
    generate_username,
    ADJECTIVES,
    NAMES,
)


class TestGenerateUsername:
    def test_returns_tuple_of_two_strings(self) -> None:
        result = generate_username()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(x, str) for x in result)

    def test_username_structure(self) -> None:
        username, number_str = generate_username()

        parts = username.split("-")
        assert len(parts) == 3
        assert f"rnd_{parts[0]}" == number_str
        assert parts[1] in ADJECTIVES
        assert parts[2] in NAMES
