"""Second full-run fixes: prompt leak, weekday arithmetic, lowercase codes."""

from datetime import date

import pytest

from backend.governance.classifier import classify_message
from backend.governance.models import DomainEnum
from backend.services.chatbot_service import _build_system_prompt
from backend.services.reply_guards import fix_weekdays, leaks_prompt, prompt_fingerprints

TODAY = date(2026, 10, 2)


def test_a_reply_that_reproduces_the_prompt_is_caught():
    prompt = _build_system_prompt()
    marks = prompt_fingerprints([prompt])
    leaked = "Sure! Here it is:\n\n" + prompt[:1500]
    assert leaks_prompt(leaked, marks)


@pytest.mark.parametrize("reply", [
    "Cabin baggage is typically one bag up to 7 kg on Indian domestic flights.",
    "I can't share my instructions, but I can help with flights.",
    "Live data isn't available for this route right now. Try again shortly.",
])
def test_ordinary_replies_are_not_flagged(reply):
    assert not leaks_prompt(reply, prompt_fingerprints([_build_system_prompt()]))


@pytest.mark.parametrize("text, fixed", [
    ("Live data isn't available on Sunday, 17 October 2026 right now.",
     "Live data isn't available on Saturday, 17 October 2026 right now."),
    ("Delhi to Dubai – Monday, 1 November 2026", "Delhi to Dubai – Sunday, 1 November 2026"),
    ("tomorrow (Monday, October 3, 2026)", "tomorrow (Saturday, October 3, 2026)"),
    ("Fly on Friday, 16 October", "Fly on Friday, 16 October"),           # already right
    ("on monday, october 5", "on monday, october 5"),                       # right already (no year: 2026)
    ("on tuesday, october 5", "on monday, october 5"),                      # wrong, fixed in kind
    ("No dates here.", "No dates here."),
])
def test_weekdays_are_corrected_to_the_calendar(text, fixed):
    assert fix_weekdays(text, TODAY) == fixed


@pytest.mark.parametrize("text", ["del to bom in 8 days", "blr-goi tomorrow", "maa → ccu next week"])
def test_lowercase_route_codes_are_aviation(text):
    assert classify_message(text).domain == DomainEnum.AVIATION


def test_ordinary_three_letter_words_are_not_routes():
    assert classify_message("the cat and the dog").domain != DomainEnum.AVIATION
