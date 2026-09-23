"""Conservative replies grounded in the immutable Saqta starter kit."""

import json
import re
from datetime import date
from pathlib import Path

from contracts.models import Decision, Scenario


DATA_DATE = date(2026, 10, 1)


class ReplyComposer:
    def __init__(self, mock_path: Path):
        self.mock = json.loads(mock_path.read_text(encoding="utf-8"))
        self.knowledge = json.loads(mock_path.with_name("knowledge_base.json").read_text(encoding="utf-8"))

    def compose(self, decision: Decision, catalog: list[Scenario], language: str,
                utterance: str = "") -> str:
        lang = self.reply_language(language, utterance)
        selected = decision.selected_scenario_id
        if decision.action == "clarify":
            return decision.clarification_question or self._say(lang, "Уточните ваш вопрос.",
                                                               "Сұрағыңызды нақтылаңызшы.",
                                                               "Could you clarify your request?")
        if selected == "SYS_GOODBYE":
            return self._say(lang, "Спасибо за обращение! Хорошего дня.",
                             "Хабарласқаныңызға рақмет! Күніңіз сәтті өтсін.",
                             "Thanks for contacting Saqta. Have a good day!")
        if selected == "SYS_OUT_OF_SCOPE":
            return self._say(lang,
                             "Помогу с вопросами страхования Saqta, но не с этим запросом.",
                             "Saqta сақтандыруы бойынша көмектесемін, бірақ бұл сұраққа емес.",
                             "I can help with Saqta insurance, but not that request.")
        if decision.action == "transfer" or selected == "SC37":
            return self._say(lang,
                             "Подготовлю для оператора краткое содержание разговора. В этом демо реального соединения нет.",
                             "Операторға сөйлесудің қысқаша мазмұнын дайындаймын. Бұл демода нақты қосудың мүмкіндігі жоқ.",
                             "I will prepare a summary for an operator. This demo cannot connect a real operator.")
        if selected == "SC25":
            status = self._policy_status(decision, lang)
            if "SC29" in decision.scenario_ids:
                status += " " + self._say(
                    lang,
                    "Затем помогу сменить телефон; изменение потребует отдельного подтверждения.",
                    "Содан кейін телефонды өзгертуге көмектесемін; өзгеріс бөлек растауды қажет етеді.",
                    "Then I can help change your phone number; the change requires separate confirmation.",
                )
            return status
        if selected == "SC17":
            return self._claim_status(decision, lang)
        if selected == "SC31":
            return self._payment_methods(lang)
        if selected == "SC33":
            return self._office(decision, lang)

        by_id = {scenario.id: scenario for scenario in catalog}
        prompts = []
        for scenario_id in decision.scenario_ids[:2]:
            scenario = by_id.get(scenario_id)
            if not scenario or scenario_id.startswith("SYS_"):
                continue
            if lang == "en":
                prompts.append(f"I can help with {scenario.purpose.lower()}. What details can you provide?")
            else:
                localized = scenario.source.get("responses", {}).get(lang, {})
                opening = localized.get("opening")
                if opening:
                    prompts.append(opening)
        if prompts:
            return " ".join(dict.fromkeys(prompts))[:500]
        return self._say(lang, "Уточните, пожалуйста, что нужно сделать.",
                         "Не істеу керегін нақтылап жіберіңізші.",
                         "Please clarify what you would like to do.")

    def _policy_status(self, decision: Decision, lang: str) -> str:
        slots = {slot.name: slot.value.strip() for slot in decision.slots}
        number = slots.get("policy_number", "").upper()
        phone = slots.get("phone", "").replace(" ", "")
        if not number or not phone:
            return self._say(lang,
                             "Для проверки назовите номер полиса и привязанный к нему телефон.",
                             "Тексеру үшін полис нөмірін және оған тіркелген телефонды айтыңыз.",
                             "Please provide the policy number and its registered phone number.")
        policy = next((p for p in self.mock["policies"] if p["policy_number"] == number), None)
        client = next((c for c in self.mock["clients"] if c["phone"] == phone), None)
        if policy is None or client is None or policy["client_id"] != client["client_id"]:
            return self._say(lang,
                             "Не удалось сопоставить полис и телефон. Проверьте данные или обратитесь к оператору.",
                             "Полис пен телефон сәйкес келмеді. Деректерді тексеріңіз немесе операторға хабарласыңыз.",
                             "The policy and phone did not match. Check the details or contact an operator.")
        end_date = date.fromisoformat(policy["end_date"])
        start_date = date.fromisoformat(policy["start_date"])
        active = start_date <= DATA_DATE <= end_date
        if active:
            return self._say(lang,
                             f"По данным демо на {DATA_DATE}: полис {number} действует до {end_date}.",
                             f"{DATA_DATE} күнгі демо дерегі бойынша {number} полисі {end_date} дейін жарамды.",
                             f"In demo data as of {DATA_DATE}, policy {number} is active until {end_date}.")
        return self._say(lang,
                         f"По данным демо на {DATA_DATE}: полис {number} не действует. Дата окончания: {end_date}.",
                         f"{DATA_DATE} күнгі демо дерегі бойынша {number} полисі жарамсыз. Аяқталу күні: {end_date}.",
                         f"In demo data as of {DATA_DATE}, policy {number} is not active. End date: {end_date}.")

    def _claim_status(self, decision: Decision, lang: str) -> str:
        slots = {slot.name: slot.value.strip() for slot in decision.slots}
        claim_number = slots.get("claim_number", "").upper()
        phone = slots.get("phone", "").replace(" ", "")
        if not claim_number or not phone:
            return self._say(lang,
                             "Для проверки назовите номер обращения и зарегистрированный телефон.",
                             "Тексеру үшін өтініш нөмірін және тіркелген телефонды айтыңыз.",
                             "Please provide your claim number and registered phone number.")
        claim = next((c for c in self.mock["claims"] if c["claim_number"] == claim_number), None)
        client = next((c for c in self.mock["clients"] if c["phone"] == phone), None)
        if claim is None or client is None or claim["client_id"] != client["client_id"]:
            return self._say(lang,
                             "Не удалось сопоставить обращение и телефон. Проверьте данные или обратитесь к оператору.",
                             "Өтініш пен телефон сәйкес келмеді. Деректерді тексеріңіз немесе операторға хабарласыңыз.",
                             "The claim and phone did not match. Check the details or contact an operator.")
        status = claim["status"]
        return self._say(lang,
                         f"По данным демо на {DATA_DATE}, статус обращения {claim_number}: {status}.",
                         f"{DATA_DATE} күнгі демо дерегі бойынша {claim_number} өтінішінің мәртебесі: {status}.",
                         f"In demo data as of {DATA_DATE}, claim {claim_number} has status: {status}.")

    def _payment_methods(self, lang: str) -> str:
        payment = self.knowledge["payments"]
        # These terms are deliberately grounded in payments.methods/installments.
        assert len(payment["methods"]) >= 3 and payment["installments"]["ogpo"]
        return self._say(lang,
                         "Оплата возможна картой в приложении или на сайте, по SMS-ссылке и в офисе. Наличные не принимаются. ОГПО оплачивается полностью; КАСКО — в 2 или 4 платежа без переплаты.",
                         "Қосымшада не сайтта картамен, SMS-сілтеме арқылы немесе кеңседе төлеуге болады. Қолма-қол ақша қабылданбайды. ОГПО толық төленеді; КАСКО-ны 2 не 4 бөлікке бөлуге болады.",
                         "Pay by card in the app or website, by SMS link, or at an office. Cash is not accepted. OGPO requires full payment; CASCO allows 2 or 4 equal payments.")

    def _office(self, decision: Decision, lang: str) -> str:
        slots = {slot.name: slot.value.strip().casefold() for slot in decision.slots}
        raw_city = slots.get("city", "")
        aliases = {"алматы": "almaty", "астана": "astana", "шымкент": "shymkent",
                   "қарағанды": "karaganda", "караганда": "karaganda"}
        city = aliases.get(raw_city, raw_city)
        if not city:
            return self._say(lang, "В каком городе ищете офис Saqta?",
                             "Saqta кеңсесін қай қаладан іздейсіз?",
                             "Which city should I check for a Saqta office?")
        office = next((o for o in self.knowledge["offices"] if o["city"].casefold() == city), None)
        if office is None:
            return self._say(lang, "В этом городе офис не найден. Уточните город или обратитесь к оператору.",
                             "Бұл қалада кеңсе табылмады. Қаланы нақтылаңыз немесе операторға хабарласыңыз.",
                             "No office was found in that city. Check the city or contact an operator.")
        return self._say(lang,
                         f"Офис Saqta в {office['city']}: {office['address']}. Часы: {office['hours']}.",
                         f"{office['city']} қаласындағы Saqta кеңсесі: {office['address']}. Жұмыс уақыты: {office['hours']}.",
                         f"Saqta office in {office['city']}: {office['address']}. Hours: {office['hours']}.")

    @staticmethod
    def _say(lang: str, ru: str, kk: str, en: str) -> str:
        return {"ru": ru, "kk": kk, "en": en}[lang]

    @staticmethod
    def reply_language(language: str, utterance: str) -> str:
        """Choose response language only; never use this heuristic to select a route."""
        if language in {"ru", "kk", "en"}:
            return language
        if re.search("[ӘәҒғҚқҢңӨөҰұҮүҺһІі]", utterance):
            return "kk"
        if language == "mixed" and re.search("[А-Яа-я]", utterance):
            return "ru"
        if language == "mixed" and re.search("[A-Za-z]", utterance):
            return "en"
        return "ru"
