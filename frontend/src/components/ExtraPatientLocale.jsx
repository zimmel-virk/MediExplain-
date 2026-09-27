import { useEffect } from 'react'
import { useAuth } from '../api/auth'

// This component provides additional patient-interface localisation for Arabic,
// Pashto and Sindhi users. It keeps a fixed set of translated interface labels,
// applies them to visible text and selected accessibility attributes according to
// the patient's preferred language, and watches for new interface content so
// dynamically rendered elements receive the same translations. Original text,
// attributes and document-language settings are restored when the localisation
// effect is removed.

const COPY = {
  ar: {
    "Patient communication platform":"منصة التواصل مع المريض",
    "Dashboard":"لوحة التحكم",
    "My reminders":"تذكيراتي",
    "Learning centre":"مركز التعلّم",
    "Support & safety":"الدعم والسلامة",
    "Sign out":"تسجيل الخروج",
    "SECURE · MULTILINGUAL · REVIEW-FIRST":"آمن · متعدد اللغات · المراجعة أولاً",
    "My care hub":"بوابة الرعاية الخاصة بي",
    "Your doctor-released summaries, medication information and learning resources.":"ملخصات الطبيب الصادرة ومعلومات الأدوية وموارد التعلّم.",
    "Open learning centre":"فتح مركز التعلّم",
    "Cases visible":"الاستشارات الظاهرة",
    "Released / complete":"صادرة / مكتملة",
    "Needs workflow action":"تحتاج إلى إجراء",
    "Role":"الدور",
    "patient":"مريض",
    "My released consultations":"استشاراتي الصادرة",
    "Open a case to see the information available to your role.":"افتح الاستشارة لعرض المعلومات المتاحة لك.",
    "Loading consultations…":"جارٍ تحميل الاستشارات…",
    "No consultations yet":"لا توجد استشارات حتى الآن",
    "New cases will appear here.":"ستظهر الاستشارات الجديدة هنا.",
    "Case":"الاستشارة",
    "Status":"الحالة",
    "Language":"اللغة",
    "Created":"تاريخ الإنشاء",
    "Action":"الإجراء",
    "Open case →":"فتح الاستشارة ←",
    "Your consultation":"استشارتك",
    "Your doctor-approved summary":"ملخصك المعتمد من الطبيب",
    "Listen to your summary":"استمع إلى ملخصك",
    "Audio is unavailable for this saved summary. The approved text remains available.":"الصوت غير متاح لهذا الملخص المحفوظ. يظل النص المعتمد متاحاً.",
    "Switch language":"تغيير اللغة",
    "Your medications":"أدويتك",
    "None recorded.":"لا توجد أدوية مسجلة.",
    "Medicine":"الدواء",
    "Dose":"الجرعة",
    "How often":"عدد المرات",
    "Timing":"التوقيت",
    "Duration":"المدة",
    "Medication timetable & reminders":"جدول الأدوية والتذكيرات",
    "Warning signs your doctor discussed":"علامات التحذير التي ناقشها طبيبك",
    "Glossary":"المصطلحات",
    "Download my summary as PDF":"تنزيل ملخصي بصيغة PDF",
    "PATIENT MEDICATION SUPPORT":"دعم أدوية المريض",
    "Medication reminders from released consultations.":"تذكيرات الأدوية من الاستشارات الصادرة.",
    "Important":"مهم",
    "Follow doctor-confirmed instructions.":"اتبع التعليمات التي أكدها الطبيب.",
    "Active medication schedules":"جداول الأدوية النشطة",
    "No active schedule.":"لا يوجد جدول دواء نشط.",
    "Medicines scheduled":"الأدوية المجدولة",
    "Pending reminder events":"التذكيرات المعلقة",
    "Loading schedules…":"جارٍ تحميل الجداول…",
    "MEDICATION":"الدواء",
    "Instructions only":"تعليمات فقط",
    "Dose / strength":"الجرعة / القوة",
    "Form":"الشكل",
    "PRN / as-needed instruction — no invented fixed alarms.":"دواء عند الحاجة — لا يتم إنشاء منبه ثابت غير مؤكد.",
    "Upcoming reminder times":"مواعيد التذكير القادمة",
    "No pending events.":"لا توجد تذكيرات معلقة.",
    "Medication schedule":"جدول الأدوية",
    "Medication schedules":"جداول الأدوية",
    "Frequency":"التكرار",
    "Food instruction":"تعليمات الطعام",
    "Start date":"تاريخ البدء",
    "End date":"تاريخ الانتهاء",
    "Doctor-approved instructions:":"تعليمات معتمدة من الطبيب:",
    "Reminder dates and times":"تواريخ وأوقات التذكير",
    "Date":"التاريخ",
    "Time":"الوقت",
    "Next alert":"التنبيه التالي",
    "Actions":"الإجراءات",
    "Medication reminders":"تذكيرات الأدوية",
    "Enable alarm sound, spoken reminders and browser notifications.":"فعّل صوت المنبه والتذكيرات الصوتية وإشعارات المتصفح.",
    "Enable alarms & voice":"تفعيل المنبه والصوت",
    "Medication alarms enabled":"منبهات الأدوية مفعّلة",
    "Alarm":"المنبه",
    "Voice":"الصوت",
    "Test voice":"اختبار الصوت",
    "Medication Reminder":"تذكير الدواء",
    "Take":"تناول",
    "Due:":"الموعد:",
    "Taken":"تم التناول",
    "Snooze 10 min":"تأجيل 10 دقائق",
    "Skip":"تخطي",
    "Repeat voice":"إعادة الصوت",
    "Taken all":"تم تناول الكل",
    "Snooze all 10 min":"تأجيل الكل 10 دقائق",
    "Skip all":"تخطي الكل",
    "PATIENT EDUCATION · SOFTWARE GUIDANCE":"تثقيف المريض · إرشادات استخدام النظام",
    "Patient Learning Centre":"مركز تعلّم المريض",
    "Simple guidance for using MediExplain+.":"إرشادات بسيطة لاستخدام MediExplain+.",
    "Learning language":"لغة التعلّم",
    "Frequently asked questions":"الأسئلة الشائعة",
    "FAQ":"الأسئلة الشائعة",
    "Remember":"تذكّر",
    "SUPPORT · PRIVACY · SAFETY":"الدعم · الخصوصية · السلامة",
    "Support & Safety Centre":"مركز الدعم والسلامة",
    "Report a privacy concern, get help, flag a problem or contact the project team from one place.":"أبلغ عن مشكلة خصوصية أو اطلب المساعدة أو أبلغ عن مشكلة من مكان واحد.",
    "Report a privacy concern":"الإبلاغ عن مشكلة خصوصية",
    "Report a technical problem":"الإبلاغ عن مشكلة تقنية",
    "Tell us about errors, broken pages, audio issues, reminders or unexpected system behaviour.":"أخبرنا عن الأخطاء أو الصفحات المعطلة أو مشاكل الصوت أو التذكيرات.",
    "Get help":"الحصول على المساعدة",
    "Ask for help using your dashboard, patient portal, assistant review or reminder features.":"اطلب المساعدة في استخدام لوحة التحكم أو بوابة المريض أو التذكيرات.",
    "pending":"قيد الانتظار",
    "snoozed":"مؤجل",
    "taken":"تم التناول",
    "skipped":"تم التخطي",
    "released":"تم الإصدار",
    "approved":"معتمد",
    "under cross check":"قيد المراجعة الإضافية",
    "cross checked":"تمت المراجعة الإضافية"
  },

  ps: {
    "Patient communication platform":"د ناروغ د اړیکو پلیټفارم",
    "Dashboard":"ډشبورډ",
    "My reminders":"زما یادونې",
    "Learning centre":"د زده کړې مرکز",
    "Support & safety":"مرسته او خوندیتوب",
    "Sign out":"وتل",
    "SECURE · MULTILINGUAL · REVIEW-FIRST":"خوندي · څو ژبنی · لومړی بیاکتنه",
    "My care hub":"زما د پاملرنې مرکز",
    "Your doctor-released summaries, medication information and learning resources.":"ستاسو د ډاکټر لخوا خپاره شوي لنډیزونه، د درملو معلومات او د زده کړې سرچینې.",
    "Open learning centre":"د زده کړې مرکز پرانیزئ",
    "Cases visible":"ښکاره مشورې",
    "Released / complete":"خپرې شوې / بشپړې",
    "Needs workflow action":"عمل ته اړتیا لري",
    "Role":"رول",
    "patient":"ناروغ",
    "My released consultations":"زما خپرې شوې مشورې",
    "Open a case to see the information available to your role.":"مشوره پرانیزئ ترڅو خپل معلومات وګورئ.",
    "Loading consultations…":"مشورې پورته کېږي…",
    "No consultations yet":"تر اوسه مشوره نشته",
    "New cases will appear here.":"نوې مشورې به دلته ښکاره شي.",
    "Case":"مشوره",
    "Status":"حالت",
    "Language":"ژبه",
    "Created":"جوړه شوې",
    "Action":"عمل",
    "Open case →":"مشوره پرانیزئ ←",
    "Your consultation":"ستاسو مشوره",
    "Your doctor-approved summary":"ستاسو د ډاکټر تایید شوی لنډیز",
    "Listen to your summary":"خپل لنډیز واورئ",
    "Audio is unavailable for this saved summary. The approved text remains available.":"د دې خوندي شوي لنډیز لپاره غږ نشته. تایید شوی لیکلی متن لا هم شته.",
    "Switch language":"ژبه بدله کړئ",
    "Your medications":"ستاسو درمل",
    "None recorded.":"هیڅ درمل ثبت شوي نه دي.",
    "Medicine":"درمل",
    "Dose":"دوز",
    "How often":"څو ځله",
    "Timing":"وخت",
    "Duration":"موده",
    "Medication timetable & reminders":"د درملو مهالویش او یادونې",
    "Warning signs your doctor discussed":"هغه د خطر نښې چې ډاکټر مو تشریح کړې",
    "Glossary":"لغتنامه",
    "Download my summary as PDF":"زما لنډیز د PDF په توګه ښکته کړئ",
    "PATIENT MEDICATION SUPPORT":"د ناروغ د درملو ملاتړ",
    "Medication reminders from released consultations.":"د خپرو شوو مشورو د درملو یادونې.",
    "Important":"مهم",
    "Follow doctor-confirmed instructions.":"د ډاکټر تایید شوې لارښوونې تعقیب کړئ.",
    "Active medication schedules":"فعال د درملو مهالویشونه",
    "No active schedule.":"هیڅ فعال مهالویش نشته.",
    "Medicines scheduled":"مهالویش شوي درمل",
    "Pending reminder events":"پاتې یادونې",
    "Loading schedules…":"مهالویشونه پورته کېږي…",
    "MEDICATION":"درمل",
    "Instructions only":"یوازې لارښوونې",
    "Dose / strength":"دوز / ځواک",
    "Form":"بڼه",
    "PRN / as-needed instruction — no invented fixed alarms.":"د اړتیا پر مهال درمل — ثابت الارم نه جوړېږي.",
    "Upcoming reminder times":"راتلونکې یادونې",
    "No pending events.":"هیڅ پاتې یادونه نشته.",
    "Medication schedule":"د درملو مهالویش",
    "Medication schedules":"د درملو مهالویشونه",
    "Frequency":"تکرار",
    "Food instruction":"د خوړو لارښوونه",
    "Start date":"د پیل نېټه",
    "End date":"د پای نېټه",
    "Doctor-approved instructions:":"د ډاکټر تایید شوې لارښوونې:",
    "Reminder dates and times":"د یادونو نېټې او وختونه",
    "Date":"نېټه",
    "Time":"وخت",
    "Next alert":"راتلونکی خبرتیا",
    "Actions":"عملونه",
    "Medication reminders":"د درملو یادونې",
    "Enable alarm sound, spoken reminders and browser notifications.":"الارم، غږیزې یادونې او د براوزر خبرتیاوې فعالې کړئ.",
    "Enable alarms & voice":"الارم او غږ فعال کړئ",
    "Medication alarms enabled":"د درملو الارمونه فعال دي",
    "Alarm":"الارم",
    "Voice":"غږ",
    "Test voice":"غږ وازمویئ",
    "Medication Reminder":"د درملو یادونه",
    "Take":"واخلئ",
    "Due:":"وخت:",
    "Taken":"واخیستل شو",
    "Snooze 10 min":"۱۰ دقیقې وروسته",
    "Skip":"پرېږدئ",
    "Repeat voice":"غږ بیا واورئ",
    "Taken all":"ټول واخیستل شول",
    "Snooze all 10 min":"ټول ۱۰ دقیقې وروسته",
    "Skip all":"ټول پرېږدئ",
    "PATIENT EDUCATION · SOFTWARE GUIDANCE":"د ناروغ زده کړه · د سیسټم لارښوونه",
    "Patient Learning Centre":"د ناروغ د زده کړې مرکز",
    "Simple guidance for using MediExplain+.":"د MediExplain+ د استعمال ساده لارښوونې.",
    "Learning language":"د زده کړې ژبه",
    "Frequently asked questions":"ډېرې پوښتل شوې پوښتنې",
    "FAQ":"پوښتنې",
    "Remember":"په یاد ولرئ",
    "SUPPORT · PRIVACY · SAFETY":"مرسته · محرمیت · خوندیتوب",
    "Support & Safety Centre":"د مرستې او خوندیتوب مرکز",
    "Report a privacy concern, get help, flag a problem or contact the project team from one place.":"د محرمیت ستونزه راپور کړئ، مرسته ترلاسه کړئ یا تخنیکي ستونزه ثبت کړئ.",
    "Report a privacy concern":"د محرمیت ستونزه راپور کړئ",
    "Report a technical problem":"تخنیکي ستونزه راپور کړئ",
    "Tell us about errors, broken pages, audio issues, reminders or unexpected system behaviour.":"د تېروتنو، خرابو پاڼو، غږ، یادونو یا ناڅاپي ستونزو په اړه ووایئ.",
    "Get help":"مرسته ترلاسه کړئ",
    "Ask for help using your dashboard, patient portal, assistant review or reminder features.":"د ډشبورډ، ناروغ پورټل یا یادونو په کارولو کې مرسته وغواړئ.",
    "pending":"پاتې",
    "snoozed":"ځنډول شوی",
    "taken":"واخیستل شو",
    "skipped":"پرېښودل شو",
    "released":"خپور شوی",
    "approved":"تایید شوی",
    "under cross check":"د بیاکتنې لاندې",
    "cross checked":"بیاکتل شوی"
  },

  sd: {
    "Patient communication platform":"مريض رابطي جو پليٽفارم",
    "Dashboard":"ڊيش بورڊ",
    "My reminders":"منهنجون ياد ڏيارڻيون",
    "Learning centre":"سکيا مرڪز",
    "Support & safety":"مدد ۽ حفاظت",
    "Sign out":"سائن آئوٽ",
    "SECURE · MULTILINGUAL · REVIEW-FIRST":"محفوظ · گهڻ ٻولي · پهرين جائزو",
    "My care hub":"منهنجو سنڀال پورٽل",
    "Your doctor-released summaries, medication information and learning resources.":"ڊاڪٽر طرفان جاري ڪيل خلاصا، دوائن جي معلومات ۽ سکيا جا وسيلا.",
    "Open learning centre":"سکيا مرڪز کوليو",
    "Cases visible":"نظر ايندڙ صلاح مشورا",
    "Released / complete":"جاري / مڪمل",
    "Needs workflow action":"عمل جي ضرورت",
    "Role":"ڪردار",
    "patient":"مريض",
    "My released consultations":"منهنجون جاري ڪيل صلاح مشورا",
    "Open a case to see the information available to your role.":"پنهنجي معلومات ڏسڻ لاءِ صلاح مشورو کوليو.",
    "Loading consultations…":"صلاح مشورا لوڊ ٿي رهيا آهن…",
    "No consultations yet":"اڃا ڪا صلاح مشورو ناهي",
    "New cases will appear here.":"نوان ڪيس هتي ظاهر ٿيندا.",
    "Case":"صلاح مشورو",
    "Status":"حالت",
    "Language":"ٻولي",
    "Created":"ٺهيل",
    "Action":"عمل",
    "Open case →":"صلاح مشورو کوليو ←",
    "Your consultation":"توهان جي صلاح مشورو",
    "Your doctor-approved summary":"ڊاڪٽر طرفان تصديق ٿيل توهان جو خلاصو",
    "Listen to your summary":"پنهنجو خلاصو ٻڌو",
    "Audio is unavailable for this saved summary. The approved text remains available.":"هن محفوظ ٿيل خلاصي لاءِ آڊيو موجود ناهي. تصديق ٿيل لکيل متن موجود آهي.",
    "Switch language":"ٻولي تبديل ڪريو",
    "Your medications":"توهان جون دوائون",
    "None recorded.":"ڪا دوا درج ٿيل ناهي.",
    "Medicine":"دوا",
    "Dose":"خوراک",
    "How often":"ڪيترا ڀيرا",
    "Timing":"وقت",
    "Duration":"مدت",
    "Medication timetable & reminders":"دوائن جو شيڊول ۽ ياد ڏيارڻيون",
    "Warning signs your doctor discussed":"خطري جون نشانيون جيڪي ڊاڪٽر ٻڌايون",
    "Glossary":"لغت",
    "Download my summary as PDF":"منهنجو خلاصو PDF طور ڊائون لوڊ ڪريو",
    "PATIENT MEDICATION SUPPORT":"مريض لاءِ دوائن جي مدد",
    "Medication reminders from released consultations.":"جاري ٿيل صلاح مشورن مان دوائن جون ياد ڏيارڻيون.",
    "Important":"اهم",
    "Follow doctor-confirmed instructions.":"ڊاڪٽر جي تصديق ٿيل هدايتن تي عمل ڪريو.",
    "Active medication schedules":"فعال دوائن جا شيڊول",
    "No active schedule.":"ڪو فعال شيڊول موجود ناهي.",
    "Medicines scheduled":"شيڊول ڪيل دوائون",
    "Pending reminder events":"باقي ياد ڏيارڻيون",
    "Loading schedules…":"شيڊول لوڊ ٿي رهيا آهن…",
    "MEDICATION":"دوا",
    "Instructions only":"صرف هدايتون",
    "Dose / strength":"خوراک / طاقت",
    "Form":"قسم",
    "PRN / as-needed instruction — no invented fixed alarms.":"ضرورت مطابق دوا — مقرر الارم نه ٺهندو.",
    "Upcoming reminder times":"ايندڙ ياد ڏيارڻيون",
    "No pending events.":"ڪا باقي ياد ڏيارڻي ناهي.",
    "Medication schedule":"دوائن جو شيڊول",
    "Medication schedules":"دوائن جا شيڊول",
    "Frequency":"تعداد",
    "Food instruction":"کاڌي جي هدايت",
    "Start date":"شروع جي تاريخ",
    "End date":"ختم ٿيڻ جي تاريخ",
    "Doctor-approved instructions:":"ڊاڪٽر جي تصديق ٿيل هدايتون:",
    "Reminder dates and times":"ياد ڏيارڻ جون تاريخون ۽ وقت",
    "Date":"تاريخ",
    "Time":"وقت",
    "Next alert":"اڳيون اطلاع",
    "Actions":"عمل",
    "Medication reminders":"دوائن جون ياد ڏيارڻيون",
    "Enable alarm sound, spoken reminders and browser notifications.":"الارم، آواز واريون ياد ڏيارڻيون ۽ برائوزر اطلاع فعال ڪريو.",
    "Enable alarms & voice":"الارم ۽ آواز فعال ڪريو",
    "Medication alarms enabled":"دوائن جا الارم فعال آهن",
    "Alarm":"الارم",
    "Voice":"آواز",
    "Test voice":"آواز آزمايو",
    "Medication Reminder":"دوا جي ياد ڏيارڻي",
    "Take":"وٺو",
    "Due:":"وقت:",
    "Taken":"ورتي وئي",
    "Snooze 10 min":"10 منٽ پوءِ",
    "Skip":"ڇڏي ڏيو",
    "Repeat voice":"آواز ٻيهر ٻڌو",
    "Taken all":"سڀ ورتيون ويون",
    "Snooze all 10 min":"سڀ 10 منٽ پوءِ",
    "Skip all":"سڀ ڇڏي ڏيو",
    "PATIENT EDUCATION · SOFTWARE GUIDANCE":"مريض سکيا · سسٽم جي رهنمائي",
    "Patient Learning Centre":"مريض سکيا مرڪز",
    "Simple guidance for using MediExplain+.":"MediExplain+ استعمال ڪرڻ لاءِ سادي رهنمائي.",
    "Learning language":"سکيا جي ٻولي",
    "Frequently asked questions":"اڪثر پڇيا ويندڙ سوال",
    "FAQ":"سوال",
    "Remember":"ياد رکو",
    "SUPPORT · PRIVACY · SAFETY":"مدد · رازداري · حفاظت",
    "Support & Safety Centre":"مدد ۽ حفاظت مرڪز",
    "Report a privacy concern, get help, flag a problem or contact the project team from one place.":"رازداري جي مسئلي جي رپورٽ ڪريو، مدد وٺو يا فني مسئلو ٻڌايو.",
    "Report a privacy concern":"رازداري جو مسئلو رپورٽ ڪريو",
    "Report a technical problem":"فني مسئلو رپورٽ ڪريو",
    "Tell us about errors, broken pages, audio issues, reminders or unexpected system behaviour.":"غلطيون، خراب صفحا، آڊيو مسئلا، ياد ڏيارڻيون يا غير متوقع مسئلا ٻڌايو.",
    "Get help":"مدد حاصل ڪريو",
    "Ask for help using your dashboard, patient portal, assistant review or reminder features.":"ڊيش بورڊ، مريض پورٽل يا ياد ڏيارڻين جي استعمال لاءِ مدد وٺو.",
    "pending":"باقي",
    "snoozed":"ملتوي",
    "taken":"ورتي وئي",
    "skipped":"ڇڏي وئي",
    "released":"جاري ٿيل",
    "approved":"تصديق ٿيل",
    "under cross check":"ٻيهر جائزي هيٺ",
    "cross checked":"ٻيهر جائزو ٿيل"
  }
}


function normalized(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, ' ')
}


function translateValue(value, table, language) {
  const key =
    normalized(value)

  if (!key) {
    return null
  }

  if (table[key]) {
    return table[key]
  }

  const consultation =
    key.match(
      /^Consultation #(\d+)$/
    )

  if (consultation) {
    if (language === 'ar') {
      return `الاستشارة #${consultation[1]}`
    }

    if (language === 'ps') {
      return `مشوره #${consultation[1]}`
    }

    if (language === 'sd') {
      return `صلاح مشورو #${consultation[1]}`
    }
  }

  return null
}


function translatedNodeValue(
  raw,
  translated
) {
  const leading =
    raw.match(/^\s*/)?.[0]
    || ''

  const trailing =
    raw.match(/\s*$/)?.[0]
    || ''

  return (
    leading
    + translated
    + trailing
  )
}


export default function ExtraPatientLocale() {
  const { user } =
    useAuth()

  useEffect(
    () => {
      if (
        user?.role !== 'patient'
        || !COPY[
          user?.preferred_language
        ]
      ) {
        return undefined
      }

      const language =
        user.preferred_language

      const table =
        COPY[language]

      const textOriginals =
        new Map()

      const attributeOriginals =
        []
const originalLanguage =
        document.documentElement
          .getAttribute('lang')
document.documentElement
        .setAttribute(
          'lang',
          language
        )

      document.body
        .setAttribute(
          'data-mxp-patient-locale',
          language
        )

      function applyText(node) {
        if (
          !node
          || node.nodeType
          !== Node.TEXT_NODE
        ) {
          return
        }

        const parent =
          node.parentElement

        if (!parent) {
          return
        }

        if (
          [
            'SCRIPT',
            'STYLE',
            'TEXTAREA',
          ].includes(
            parent.tagName
          )
        ) {
          return
        }

        const translated =
          translateValue(
            node.nodeValue,
            table,
            language
          )

        if (
          !translated
          || normalized(
            node.nodeValue
          ) === translated
        ) {
          return
        }

        if (
          !textOriginals.has(node)
        ) {
          textOriginals.set(
            node,
            node.nodeValue
          )
        }

        node.nodeValue =
          translatedNodeValue(
            node.nodeValue,
            translated
          )
      }

      function applyAttributes(element) {
        if (
          !element
          || element.nodeType
          !== Node.ELEMENT_NODE
        ) {
          return
        }

        for (
          const attribute
          of [
            'placeholder',
            'title',
            'aria-label',
          ]
        ) {
          if (
            !element.hasAttribute(
              attribute
            )
          ) {
            continue
          }

          const raw =
            element.getAttribute(
              attribute
            )

          const translated =
            translateValue(
              raw,
              table,
              language
            )

          if (!translated) {
            continue
          }

          attributeOriginals.push(
            [
              element,
              attribute,
              raw,
            ]
          )

          element.setAttribute(
            attribute,
            translated
          )
        }
      }

      function apply(root) {
        if (!root) {
          return
        }

        if (
          root.nodeType
          === Node.TEXT_NODE
        ) {
          applyText(root)
          return
        }

        if (
          root.nodeType
          !== Node.ELEMENT_NODE
          && root.nodeType
          !== Node.DOCUMENT_FRAGMENT_NODE
        ) {
          return
        }

        if (
          root.nodeType
          === Node.ELEMENT_NODE
        ) {
          applyAttributes(root)
        }

        const textWalker =
          document.createTreeWalker(
            root,
            NodeFilter.SHOW_TEXT
          )

        let textNode

        while (
          (
            textNode =
              textWalker.nextNode()
          )
        ) {
          applyText(textNode)
        }

        if (
          root.querySelectorAll
        ) {
          root
            .querySelectorAll(
              '[placeholder],'
              + '[title],'
              + '[aria-label]'
            )
            .forEach(
              applyAttributes
            )
        }
      }

      apply(
        document.body
      )

      const observer =
        new MutationObserver(
          mutations => {
            for (
              const mutation
              of mutations
            ) {
              if (
                mutation.type
                === 'characterData'
              ) {
                applyText(
                  mutation.target
                )
              }

              for (
                const node
                of mutation.addedNodes
              ) {
                apply(node)
              }
            }
          }
        )

      observer.observe(
        document.body,
        {
          childList: true,
          subtree: true,
          characterData: true,
        }
      )

      return () => {
        observer.disconnect()

        for (
          const [
            node,
            original,
          ]
          of textOriginals
        ) {
          if (
            node?.isConnected
          ) {
            node.nodeValue =
              original
          }
        }

        for (
          const [
            element,
            attribute,
            original,
          ]
          of attributeOriginals
        ) {
          if (
            element?.isConnected
          ) {
            element.setAttribute(
              attribute,
              original
            )
          }
        }
if (
          originalLanguage
          === null
        ) {
          document.documentElement
            .removeAttribute(
              'lang'
            )
        } else {
          document.documentElement
            .setAttribute(
              'lang',
              originalLanguage
            )
        }

        document.body
          .removeAttribute(
            'data-mxp-patient-locale'
          )
      }
    },
    [
      user?.role,
      user?.preferred_language,
    ]
  )

  return null
}
