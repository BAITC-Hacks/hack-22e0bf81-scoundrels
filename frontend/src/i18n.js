/**
 * Complete Internationalization (RU / KK) dictionary for RouteMap frontend.
 * Covers all UI labels, options, error notifications, and system states.
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
    serverReadyNotice: "Сервер готов: маршрутизация активна.",
    turnLimitError: "Достигнут лимит 10 реплик для текущей сессии. Пожалуйста, начните новый разговор.",
    toggleJson: "Показать raw JSON",
    toggleStructure: "Показать структуру",
    exportSession: "💾 Экспорт сессии",
    importSession: "📂 Загрузить Replay",
    
    // Status badges
    statusConnecting: "Подключение…",
    statusOnline: "Подключено",
    statusError: "Сбой соединения",
    statusUnavailable: "Сервер недоступен",
    sessionLabel: (id) => `Сессия: ${id}…`,
    sessionError: "Сессия: ошибка",

    // Microphone & Audio error messages
    micDeniedError: "Доступ к микрофону отклонен пользователем или политикой браузера.",
    micNotFoundError: "Микрофон не обнаружен на устройстве.",
    micUnsupportedError: "Запись аудио не поддерживается данным браузером (getUserMedia недоступен).",
    micGenericError: (err) => `Сбой записи звука: ${err}`,
    sttScaffoldError: "Голосовой ввод (STT) честно возвращает HTTP 501 в scaffold-режиме. Используйте текстовый ввод.",
    sttEmptyError: "Речь не распознана или была пустой. Попробуйте снова или введите текст.",
    serverConflictError: "Сервер отклонил запрос: исчерпан лимит 10 реплик (409 Conflict).",
    serverUnavailableHint: (err) => `Сервер недоступен: ${err}. Убедитесь, что запущен python run.py`,

    // Replay & Samples
    replayToolsHeading: "Инструменты Replay и образцы",
    replayBanner: "Режим Replay: отображается ранее сохраненная сессия.",
    datasetSampleBanner: (title) => `Образец из датасета (${title}) · Без вызова LLM.`,
    emptyHistoryError: "Файл не содержит записей ходов.",
    fileReadError: (err) => `Ошибка чтения файла сессии: ${err}`,

    // Language selector options
    requestLanguageOptions: {
      auto: "Автоопределение (Auto)",
      ru: "Русский (RU)",
      kk: "Қазақша (KK)",
      mixed: "Смешанный (RU + KK)",
    },

    // Dataset sample options
    datasetSampleOptions: {
      default: "Образцы датасета (dialogs_sample)",
      D03: "D03: Смена темы (SC17 → SC27 → SC18)",
      D05: "D05: Уточнение (SYS_UNCLEAR)",
      D06: "D06: Жалоба и оператор (SC35 → SC37)",
    },
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
    waitingReply: "Клиент репликасы күтілуде…",
    turnCounter: (curr, max) => `${curr} / ${max} қадам`,
    scaffoldNotice: "Scaffold режимі: LLM және дауыстық endpoints әлі қосылмаған. API келісімшарты тексерілуде.",
    liveNotice: "Live LLM режимі: маршрутизатор белсенді.",
    serverReadyNotice: "Сервер дайын: бағыттау белсенді.",
    turnLimitError: "Осы сессия үшін 10 реплика шегіне жетті. Жаңа сөйлесуді бастаңыз.",
    toggleJson: "Raw JSON көрсету",
    toggleStructure: "Құрылымды көрсету",
    exportSession: "💾 Сессияны экспорттау",
    importSession: "📂 Replay жүктеу",

    // Status badges
    statusConnecting: "Қосылуда…",
    statusOnline: "Қосылды",
    statusError: "Қосылу қатесі",
    statusUnavailable: "Сервер қолжетімсіз",
    sessionLabel: (id) => `Сессия: ${id}…`,
    sessionError: "Сессия: қате",

    // Microphone & Audio error messages
    micDeniedError: "Микрофонға кіруге пайдаланушы немесе браузер саясаты тыйым салды.",
    micNotFoundError: "Құрылғыда микрофон табылмады.",
    micUnsupportedError: "Бұл браузерде аудио жазуға қолдау көрсетілмейді (getUserMedia қолжетімсіз).",
    micGenericError: (err) => `Дыбыс жазу қатесі: ${err}`,
    sttScaffoldError: "Дауыспен енгізу (STT) scaffold режимінде HTTP 501 қайтарады. Мәтіндік енгізуді пайдаланыңыз.",
    sttEmptyError: "Сөз танылмады немесе бос болды. Қайталап көріңіз немесе мәтін енгізіңіз.",
    serverConflictError: "Сервер сұрауды қабылдамады: 10 реплика шегі таусылды (409 Conflict).",
    serverUnavailableHint: (err) => `Сервер қолжетімсіз: ${err}. Сервер іске қосылғанына көз жеткізіңіз: python run.py`,

    // Replay & Samples
    replayToolsHeading: "Replay құралдары мен үлгілер",
    replayBanner: "Replay режимі: бұрын сақталған сессия көрсетілуде.",
    datasetSampleBanner: (title) => `Датасет үлгісі (${title}) · LLM шақыруынсыз.`,
    emptyHistoryError: "Файлда қадамдар жазбасы жоқ.",
    fileReadError: (err) => `Сессия файлын оқу қатесі: ${err}`,

    // Language selector options
    requestLanguageOptions: {
      auto: "Автоматты анықтау (Auto)",
      ru: "Орысша (RU)",
      kk: "Қазақша (KK)",
      mixed: "Аралас (RU + KK)",
    },

    // Dataset sample options
    datasetSampleOptions: {
      default: "Датасет үлгілері (dialogs_sample)",
      D03: "D03: Тақырыпты ауыстыру (SC17 → SC27 → SC18)",
      D05: "D05: Нақтылау (SYS_UNCLEAR)",
      D06: "D06: Шағым және оператор (SC35 → SC37)",
    },
  },
};

/**
 * Get localized string dictionary
 * @param {'ru'|'kk'} lang
 */
export function getLocale(lang) {
  return I18N[lang] || I18N.ru;
}
