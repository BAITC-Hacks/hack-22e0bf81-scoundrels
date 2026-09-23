/**
 * Internationalization (RU / KK) dictionary for RouteMap frontend.
 */

export const I18N = {
  ru: {
    brandSub: "· Saqta Voice Router",
    brandDesc: "Интеллектуальный голосовой маршрутизатор с LLM-слоем принятия решений",
    customerHeading: "Клиентский канал",
    supervisorHeading: "Панель супервизора (Explainability)",
    languageLabel: "Язык запроса",
    inputPlaceholder: "Введите вопрос клиента (например: «Хочу рассчитать страховку ОГПО в Алматы»)",
    sendBtn: "Отправить текст",
    micBtn: "Микрофон (PTT)",
    micRecording: "Идет запись… Отпустите для отправки",
    micProcessing: "Обработка речи…",
    resetBtn: "Новый разговор",
    replyHeading: "Ответ ассистента Saqta",
    waitingReply: "Ожидание реплики клиента…",
    turnCounter: (curr, max) => `Ход ${curr} / ${max}`,
    scaffoldNotice: "Режим scaffold: LLM и голосовые endpoints ещё не подключены. Проверяется контракт API.",
    liveNotice: "Режим Live LLM: маршрутизатор активен.",
    turnLimitError: "Достигнут лимит 10 реплик для текущей сессии. Пожалуйста, начните новый разговор.",
    toggleJson: "Показать raw JSON",
    toggleStructure: "Показать структуру",
    exportSession: "Экспорт сессии",
    importSession: "Загрузить Replay",
  },
  kk: {
    brandSub: "· Saqta Voice Router",
    brandDesc: "Шешім қабылдауға арналған LLM-қабаты бар интеллектуалды дауыстық маршрутизатор",
    customerHeading: "Клиент арнасы",
    supervisorHeading: "Супервизор панелі (Explainability)",
    languageLabel: "Сұрау тілі",
    inputPlaceholder: "Клиент сұрағын енгізіңіз (мысалы: «Алматыда ОГПО сақтандыруын есептегім келеді»)",
    sendBtn: "Мәтінді жіберу",
    micBtn: "Микрофон (PTT)",
    micRecording: "Жазылуда… Жіберу үшін босатыңыз",
    micProcessing: "Дыбыс өңделуде…",
    resetBtn: "Жаңа әңгіме",
    replyHeading: "Saqta көмекшісінің жауабы",
    waitingReply: "Клиент сөзі күтілуде…",
    turnCounter: (curr, max) => `${curr} / ${max} қадам`,
    scaffoldNotice: "Scaffold режимі: LLM және дауыстық endpoints әлі қосылмаған. API келісімшарты тексерілуде.",
    liveNotice: "Live LLM режимі: маршрутизатор белсенді.",
    turnLimitError: "Осы сессия үшін 10 реплика шегіне жетті. Жаңа сөйлесуді бастаңыз.",
    toggleJson: "Raw JSON көрсету",
    toggleStructure: "Құрылымды көрсету",
    exportSession: "Сессияны жүктеу",
    importSession: "Replay жүктеу",
  },
};

/**
 * Get localized string dictionary
 * @param {'ru'|'kk'} lang
 */
export function getLocale(lang) {
  return I18N[lang] || I18N.ru;
}
