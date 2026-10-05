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


# ── Identity, small talk and sign-offs (2026-10-05) ─────────────────────────
from backend.services.reply_guards import (
    CREATOR_REPLY, GREETING_REPLY, IDENTITY_REPLY, THANKS_REPLY,
    describes_itself, identity_reply, small_talk_reply, strip_closing_offer,
)


@pytest.mark.parametrize("q", [
    "what model are you?", "which AI model are u using?", "are you chatgpt?",
    "Are you GPT-4?", "what are you powered by?", "Who are you?", "what llm do you use",
])
def test_identity_questions_get_the_fixed_reply(q):
    assert identity_reply(q) == IDENTITY_REPLY


@pytest.mark.parametrize("q", ["who made u?", "Who built you", "who created this assistant?"])
def test_creator_questions_get_the_creator_reply(q):
    assert identity_reply(q) == CREATOR_REPLY


@pytest.mark.parametrize("q", [
    "which aircraft model does IndiGo use?", "who made the A320?", "is it a good model?",
    "cheapest flight del to bom", "what can you help me with?",
])
def test_aviation_questions_are_not_identity_questions(q):
    assert identity_reply(q) is None


@pytest.mark.parametrize("q,reply", [
    ("hi", GREETING_REPLY), ("Good morning!", GREETING_REPLY), ("how are you?", GREETING_REPLY),
    ("Thanks, that was helpful!", THANKS_REPLY), ("thank you so much", THANKS_REPLY),
])
def test_small_talk_gets_fixed_replies(q, reply):
    assert small_talk_reply(q) == reply


@pytest.mark.parametrize("q", ["hi, cheapest flight to goa", "thanks, and what about tomorrow?"])
def test_small_talk_with_a_question_goes_to_the_model(q):
    assert small_talk_reply(q) is None


def test_fixed_replies_never_name_a_model():
    for text in (IDENTITY_REPLY, CREATOR_REPLY, GREETING_REPLY):
        assert not describes_itself(text)
        for word in ("gpt", "openai", "llama", "gemini", "claude", "nemotron", "groq"):
            assert word not in text.lower()


@pytest.mark.parametrize("reply,flag", [
    ("I'm powered by OpenAI's GPT-4 architecture, fine-tuned to help.", True),
    ("I am a large language model.", True),
    ("The A320 was developed by Airbus.", False),
    ("Pilots are trained by their airline.", False),
])
def test_self_descriptions_are_caught(reply, flag):
    assert describes_itself(reply) is flag


@pytest.mark.parametrize("reply,clean", [
    ("Layovers are stops.\n\nHow can I assist you with your flight plans today?", "Layovers are stops."),
    ("Fares vary. Happy travels! Let me know if you need anything else.", "Fares vary."),
    ("Sure. Let me know your travel date.", "Sure. Let me know your travel date."),
    ("Which date do you want to travel? I'm happy to help.", "Which date do you want to travel?"),
])
def test_generic_signoffs_are_removed(reply, clean):
    assert strip_closing_offer(reply) == clean
