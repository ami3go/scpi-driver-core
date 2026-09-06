from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.scpi.mnemonics import (
    HeaderPattern,
    Mnemonic,
    expand_header_aliases,
    header_matches,
    parse_header_pattern,
)

# -- the rule ---------------------------------------------------------------


@pytest.mark.parametrize("header", ["FREQ", "FREQUENCY", "freq", "frequency", "FreQuEncY"])
def test_the_short_form_and_the_whole_long_form_are_accepted(header: str) -> None:
    assert header_matches("FREQuency", header)


@pytest.mark.parametrize("header", ["FREQU", "FREQUEN", "FREQUENC", "FRE", "F"])
def test_nothing_between_the_two_forms_is_accepted(header: str) -> None:
    """SCPI allows the short form or the long form. There is no middle."""
    assert not header_matches("FREQuency", header)


def test_a_wrong_abbreviation_is_rejected() -> None:
    """The bug this catches: PFail abbreviates to PF, so PFA is a typo."""
    assert header_matches("PFail", "PF")
    assert header_matches("PFail", "PFAIL")
    assert not header_matches("PFail", "PFA")


def test_case_alone_never_decides_a_match() -> None:
    """Headers are case-insensitive on the wire, so PFAil spells PFAIL.

    Worth stating explicitly because it is easy to expect otherwise: the
    capitals in a *pattern* mark where the short form ends, but the capitals in
    a *header* carry no meaning at all. A real instrument cannot tell PFail
    from PFAil either, and neither can this.
    """
    assert header_matches("PFail", "PFAil")
    assert header_matches("PFail", "pFaIl")


# -- headers ----------------------------------------------------------------


def test_a_multi_node_header() -> None:
    pattern = "SYSTem:ALARm:ACTion:PFail"
    assert header_matches(pattern, "syst:alar:act:pf")
    assert header_matches(pattern, "SYSTEM:ALARM:ACTION:PFAIL")
    assert header_matches(pattern, "SYSTem:ALARm:ACTion:PFail")


def test_nodes_are_matched_independently() -> None:
    """A long form in one node and a short form in the next is legal."""
    assert header_matches("SYSTem:ERRor", "SYSTEM:ERR")
    assert header_matches("SYSTem:ERRor", "SYST:ERROR")


def test_a_header_with_the_wrong_number_of_nodes_does_not_match() -> None:
    assert not header_matches("SYSTem:ERRor", "SYSTem")
    assert not header_matches("SYSTem:ERRor", "SYSTem:ERRor:NEXT")


def test_a_leading_colon_is_ignored() -> None:
    """Whether a header is written from the root is not part of its spelling."""
    assert header_matches("OUTPut:STATe", ":OUTP:STAT")


def test_a_trailing_question_mark_is_ignored_on_both_sides() -> None:
    """A query and its setter are the same command."""
    assert header_matches("FREQuency", "FREQ?")
    assert header_matches("FREQuency?", "FREQ")


# -- numeric suffixes -------------------------------------------------------


def test_a_numeric_suffix_must_match() -> None:
    assert header_matches("SOURce2:VOLTage", "sour2:volt")
    assert not header_matches("SOURce2:VOLTage", "sour1:volt")
    assert not header_matches("SOURce2:VOLTage", "sour:volt")


def test_a_suffix_is_not_confused_with_the_word() -> None:
    assert header_matches("OUTPut1:ONOFF", "OUTP1:ONOFF")
    assert not header_matches("OUTPut1:ONOFF", "OUTP1:ON")


# -- patterns with no lower case --------------------------------------------


def test_an_all_capitals_pattern_accepts_only_itself() -> None:
    """No lower case means no optional part: the word is both forms.

    This is what makes the change safe to adopt. A route table written in
    capitals keeps behaving exactly as it did.
    """
    assert header_matches("ONOFF", "onoff")
    assert not header_matches("ONOFF", "ON")


def test_an_all_lower_case_pattern_accepts_only_itself() -> None:
    assert header_matches("voltage", "VOLTAGE")
    assert not header_matches("voltage", "VOLT")


# -- common commands --------------------------------------------------------


@pytest.mark.parametrize("header", ["*IDN", "*idn", "*Idn", "*IDN?"])
def test_common_commands(header: str) -> None:
    assert header_matches("*IDN", header)


def test_a_common_command_is_not_a_node() -> None:
    assert not header_matches("*IDN", "IDN")
    assert not header_matches("IDN", "*IDN")
    assert not header_matches("*IDN", "*IDNX")


def test_a_common_command_is_matched_whole() -> None:
    """*OPC has no short form; *OP is not a command."""
    assert not header_matches("*OPC", "*OP")


# -- malformed patterns are the caller's mistake ----------------------------


@pytest.mark.parametrize("pattern", ["", "   ", "?", ":", "SYSTem::ERRor", ":::"])
def test_an_unusable_pattern_is_rejected(pattern: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_header_pattern(pattern)


def test_a_pattern_whose_short_form_is_not_marked_is_rejected() -> None:
    """ONoff could mean ON or ONOFF; guessing would be worse than refusing."""
    with pytest.raises(ConfigurationError, match="ambiguous"):
        parse_header_pattern("ONoFF")


def test_a_common_command_cannot_carry_a_suffix() -> None:
    with pytest.raises(ConfigurationError, match="suffix"):
        parse_header_pattern("*IDN1")


@pytest.mark.parametrize("pattern", ["FREQ-uency", "VOLT age", "2SOURce"])
def test_a_pattern_that_is_not_a_mnemonic_is_rejected(pattern: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_header_pattern(pattern)


def test_a_malformed_header_is_simply_not_a_match() -> None:
    """It came off the wire; it is not a mistake in this program."""
    assert not header_matches("FREQuency", "FREQ-uency")
    assert not header_matches("FREQuency", "")
    assert not header_matches("SYSTem:ERRor", "SYSTem:")


# -- the parsed shape -------------------------------------------------------


def test_the_parsed_pattern_reports_both_forms() -> None:
    pattern = parse_header_pattern("SOURce2:VOLTage")
    assert pattern.nodes == (
        Mnemonic(short="SOUR", long="SOURCE", suffix="2"),
        Mnemonic(short="VOLT", long="VOLTAGE", suffix=""),
    )
    assert not pattern.is_common


def test_a_common_command_parses_as_one_node() -> None:
    pattern = parse_header_pattern("*ESR?")
    assert pattern == HeaderPattern(nodes=(Mnemonic("ESR", "ESR"),), is_common=True)


def test_parsing_is_cached_because_simulators_match_in_a_loop() -> None:
    assert parse_header_pattern("FREQuency") is parse_header_pattern("FREQuency")


# -- alias expansion --------------------------------------------------------


def test_every_combination_of_forms_is_produced() -> None:
    """Nodes are independent: instruments accept a mix."""
    assert expand_header_aliases("SYSTem:ERRor") == {
        "SYST:ERR",
        "SYST:ERROR",
        "SYSTEM:ERR",
        "SYSTEM:ERROR",
    }


def test_a_node_with_no_short_form_contributes_one_spelling() -> None:
    assert expand_header_aliases("OUTPut1:ONOFF") == {"OUTP1:ONOFF", "OUTPUT1:ONOFF"}


def test_a_common_command_expands_to_itself() -> None:
    assert expand_header_aliases("*IDN?") == {"*IDN"}


def test_every_alias_is_accepted_by_the_matcher_it_came_from() -> None:
    """The two must agree, or a table would answer headers the rule rejects."""
    for pattern in [
        "SYSTem:ALARm:ACTion:PFail",
        "SOURce2:VOLTage:AMPLitude",
        "MEASure:VOLTage:DC",
        "*ESR",
    ]:
        for alias in expand_header_aliases(pattern):
            assert header_matches(pattern, alias), (pattern, alias)


def test_aliases_are_upper_case_and_unpunctuated() -> None:
    for alias in expand_header_aliases(":OUTPut:STATe?"):
        assert alias == alias.upper()
        assert not alias.startswith(":") and not alias.endswith("?")


def test_an_absurd_pattern_is_refused_rather_than_allocated() -> None:
    with pytest.raises(ConfigurationError, match="nodes"):
        expand_header_aliases(":".join(["NODe"] * 9))


def test_the_cap_allows_what_real_instruments_use() -> None:
    assert len(expand_header_aliases(":".join(["NODe"] * 8))) == 2**8


def test_a_mnemonic_may_contain_an_underscore() -> None:
    """Tektronix spells the waveform preamble BIT_Nr, short form BIT_N.

    The underscore is part of the word, not a separator, so the required part
    still ends at the first lower-case letter.
    """
    assert parse_header_pattern("BIT_Nr").nodes == (Mnemonic("BIT_N", "BIT_NR"),)
    assert header_matches("WFMOutpre:BIT_Nr", "WFMO:BIT_N")
    assert header_matches("WFMOutpre:BIT_Nr", "WFMOUTPRE:BIT_NR")
    assert not header_matches("WFMOutpre:BIT_Nr", "WFMO:BIT")
