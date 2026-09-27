"""Patient learning-centre content.

Software/product guidance only. This page does not provide
independent medical advice, diagnosis or prescribing.
"""

# This file provides the patient Learning Centre content used in the MediExplain+ portal.
# It keeps the same guidance structure across English, Urdu, Punjabi Shahmukhi, Pashto,
# Sindhi and Arabic, covering released summaries, medication and voice reminders,
# second-opinion requests, common questions and the limits of the system. The endpoint
# selects the requested or saved patient language, falls back to English when needed,
# and returns the matching guides and FAQs without generating medical advice itself.


from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user
from app.models import User


router = APIRouter(
    prefix="/api/learning",
    tags=["learning"],
)


CONTENT = {
    "en": {
        "title": "Patient Learning Centre",
        "subtitle": (
            "Learn how to use your MediExplain+ portal "
            "safely and confidently."
        ),
        "guides": [
            {
                "title": "Open a released summary",
                "body": (
                    "Your patient dashboard only shows information "
                    "after the treating doctor has released it. "
                    "Open a consultation to read, listen, view "
                    "confirmed medicines and download the PDF."
                ),
            },
            {
                "title": "Use medication reminders",
                "body": (
                    "Reminder times come from doctor-confirmed "
                    "medicine instructions. Use Taken, Snooze or "
                    "Skip to record what happened. The system does "
                    "not invent a fixed schedule when instructions "
                    "are unclear or as-needed."
                ),
            },
            {
                "title": "Use voice reminders",
                "body": (
                    "Enable voice reminders while the portal is "
                    "open. Medicines due at the same time are "
                    "handled together and spoken reminders use "
                    "the supported patient-language audio route."
                ),
            },
            {
                "title": "Request a second opinion",
                "body": (
                    "After release, a patient may request an "
                    "authorised cross-check doctor. The second "
                    "opinion is advisory and does not silently "
                    "change the treating doctor's instructions."
                ),
            },
        ],
        "faqs": [
            {
                "q": "Can MediExplain+ diagnose me?",
                "a": (
                    "No. It is a clinician-reviewed communication "
                    "prototype. It does not independently diagnose "
                    "or prescribe."
                ),
            },
            {
                "q": "Why can I not see a new consultation yet?",
                "a": (
                    "Patients only see a consultation after the "
                    "treating doctor has reviewed and released it."
                ),
            },
            {
                "q": "What if a reminder looks wrong?",
                "a": (
                    "Follow the doctor's confirmed instructions "
                    "and contact the clinical team if something "
                    "appears incorrect or unclear."
                ),
            },
            {
                "q": "Can I download my summary?",
                "a": (
                    "Yes. Released consultations can include the "
                    "patient summary, confirmed medication "
                    "instructions and reminder information."
                ),
            },
        ],
    },

    "ur": {
        "title": "مریض سیکھنے کا مرکز",
        "subtitle": (
            "اپنے MediExplain+ پورٹل کو محفوظ اور آسان طریقے "
            "سے استعمال کرنا سیکھیں۔"
        ),
        "guides": [
            {
                "title": "جاری کردہ خلاصہ کھولیں",
                "body": (
                    "ڈاکٹر کے جاری کرنے کے بعد ہی مشاورت مریض کے "
                    "پورٹل میں نظر آتی ہے۔ خلاصہ پڑھیں، آڈیو سنیں، "
                    "تصدیق شدہ دوائیاں دیکھیں اور PDF ڈاؤن لوڈ کریں۔"
                ),
            },
            {
                "title": "ادویات کی یاددہانیاں",
                "body": (
                    "یاددہانی کے اوقات ڈاکٹر کی تصدیق شدہ ہدایات "
                    "سے بنتے ہیں۔ Taken، Snooze یا Skip استعمال کریں۔ "
                    "غیر واضح ہدایات پر سسٹم خود شیڈول نہیں بناتا۔"
                ),
            },
            {
                "title": "آواز والی یاددہانی",
                "body": (
                    "پورٹل کھلا ہو تو voice reminders فعال کیے جا "
                    "سکتے ہیں۔ مریض کی زبان کے لیے دستیاب آڈیو راستہ "
                    "استعمال کیا جاتا ہے۔"
                ),
            },
            {
                "title": "دوسری رائے",
                "body": (
                    "جاری شدہ خلاصے کے بعد مریض مجاز cross-check "
                    "ڈاکٹر سے دوسری رائے کی درخواست کر سکتا ہے۔ "
                    "یہ علاج کو خودکار طور پر تبدیل نہیں کرتی۔"
                ),
            },
        ],
        "faqs": [
            {
                "q": "کیا MediExplain+ تشخیص کرتا ہے؟",
                "a": (
                    "نہیں۔ یہ ڈاکٹر کی نگرانی میں مواصلاتی پروٹوٹائپ "
                    "ہے اور خود سے تشخیص یا نسخہ نہیں بناتا۔"
                ),
            },
            {
                "q": "نئی مشاورت کیوں نظر نہیں آ رہی؟",
                "a": (
                    "مریض صرف وہی مشاورت دیکھتا ہے جسے علاج کرنے "
                    "والے ڈاکٹر نے جائزے کے بعد جاری کیا ہو۔"
                ),
            },
            {
                "q": "اگر یاددہانی غلط لگے تو؟",
                "a": (
                    "ڈاکٹر کی تصدیق شدہ ہدایات کو ترجیح دیں اور "
                    "کلینیکل ٹیم سے رابطہ کریں۔"
                ),
            },
            {
                "q": "کیا خلاصہ PDF میں مل سکتا ہے؟",
                "a": (
                    "جی ہاں۔ جاری شدہ مشاورت کے ساتھ مریض کا "
                    "PDF دستیاب ہو سکتا ہے۔"
                ),
            },
        ],
    },

    "pa_shah": {
        "title": "مریض سکھن دا مرکز",
        "subtitle": (
            "اپنا MediExplain+ پورٹل محفوظ طریقے نال ورتنا سکھو۔"
        ),
        "guides": [
            {
                "title": "جاری کیتا خلاصہ کھولو",
                "body": (
                    "علاج کرن والا ڈاکٹر جاری کرے تاں مشاورت مریض "
                    "دے پورٹل وچ نظر آندی اے۔ خلاصہ پڑھو، آڈیو سنو، "
                    "تصدیق شدہ دوائیاں ویکھو تے PDF ڈاؤن لوڈ کرو۔"
                ),
            },
            {
                "title": "دوائی دیاں یاددہانیاں",
                "body": (
                    "یاددہانی دے وقت ڈاکٹر دیاں تصدیق شدہ ہدایتاں "
                    "توں بن دے نیں۔ Taken، Snooze تے Skip ورتو۔"
                ),
            },
            {
                "title": "آواز والی یاددہانی",
                "body": (
                    "پورٹل کھلا ہووے تاں voice reminders چالو کیتے "
                    "جا سکدے نیں۔ مریض دی زبان والا دستیاب آڈیو "
                    "استعمال ہوندا اے۔"
                ),
            },
            {
                "title": "دوجی رائے منگو",
                "body": (
                    "جاری ہوئے خلاصے توں بعد مریض مجاز cross-check "
                    "ڈاکٹر کولوں دوجی رائے منگ سکدا اے۔"
                ),
            },
        ],
        "faqs": [
            {
                "q": "کی MediExplain+ تشخیص کردا اے؟",
                "a": (
                    "نہیں۔ ایہ ڈاکٹر دی نگرانی والا communication "
                    "prototype اے تے آپ تشخیص یا نسخہ نہیں بناؤندا۔"
                ),
            },
            {
                "q": "نواں کیس کیوں نہیں دِس رہیا؟",
                "a": (
                    "مریض نوں اوہی کیس دِسدا اے جیہڑا علاج کرن والے "
                    "ڈاکٹر نے جائزے توں بعد جاری کیتا ہووے۔"
                ),
            },
            {
                "q": "جے reminder غلط لگے؟",
                "a": (
                    "ڈاکٹر دیاں تصدیق شدہ ہدایتاں نوں ترجیح دیو "
                    "تے کلینیکل ٹیم نال رابطہ کرو۔"
                ),
            },
            {
                "q": "PDF ڈاؤن لوڈ ہو سکدا اے؟",
                "a": "ہاں۔ جاری شدہ کیس دا PDF دستیاب ہو سکدا اے۔",
            },
        ],
    },

    "ps": {
        "title": "د ناروغ د زده کړې مرکز",
        "subtitle": (
            "زده کړئ چې خپل MediExplain+ پورټل څنګه په خوندي "
            "او ډاډمن ډول وکاروئ."
        ),
        "guides": [
            {
                "title": "خپور شوی لنډیز پرانیزئ",
                "body": (
                    "مشوره هغه وخت د ناروغ په پورټل کې ښکاري چې "
                    "درملنه کوونکي ډاکټر یې له کتنې وروسته خپره کړي. "
                    "لنډیز ولولئ، غږ واورئ، تایید شوي درمل وګورئ "
                    "او PDF ښکته کړئ."
                ),
            },
            {
                "title": "د درملو یادونې وکاروئ",
                "body": (
                    "د یادونې وختونه د ډاکټر له تایید شوو لارښوونو "
                    "څخه جوړېږي. Taken، Snooze یا Skip وکاروئ. "
                    "سیسټم د ناڅرګندو لارښوونو لپاره له ځانه "
                    "مهالویش نه جوړوي."
                ),
            },
            {
                "title": "غږیزې یادونې وکاروئ",
                "body": (
                    "کله چې پورټل خلاص وي، غږیزې یادونې فعالېدای "
                    "شي. غږ د ناروغ لپاره د ملاتړ شوې ژبې له "
                    "لارې وړاندې کېږي."
                ),
            },
            {
                "title": "دوهمه بیاکتنه وغواړئ",
                "body": (
                    "له خپرېدو وروسته ناروغ کولای شي له مجاز "
                    "cross-check ډاکټر څخه د دوهمې بیاکتنې غوښتنه وکړي."
                ),
            },
        ],
        "faqs": [
            {
                "q": "ایا MediExplain+ زما تشخیص کوي؟",
                "a": (
                    "نه. دا د ډاکټر تر کتنې لاندې د اړیکو پروټوټایپ "
                    "دی او په خپلواکه توګه تشخیص یا نسخه نه کوي."
                ),
            },
            {
                "q": "ولې نوې مشوره نه وینم؟",
                "a": (
                    "ناروغ یوازې هغه مشوره ویني چې ډاکټر یې له "
                    "کتنې وروسته خپره کړې وي."
                ),
            },
            {
                "q": "که یادونه ناسمه ښکاري څه وکړم؟",
                "a": (
                    "د ډاکټر تایید شوې لارښوونې تعقیب کړئ او له "
                    "کلینیکي ټیم سره اړیکه ونیسئ."
                ),
            },
            {
                "q": "ایا لنډیز PDF کې ترلاسه کولای شم؟",
                "a": "هو. د خپرې شوې مشورې PDF ترلاسه کېدای شي.",
            },
        ],
    },

    "sd": {
        "title": "مريض سکيا مرڪز",
        "subtitle": (
            "سکو ته پنهنجو MediExplain+ پورٽل محفوظ ۽ اعتماد "
            "سان ڪيئن استعمال ڪجي."
        ),
        "guides": [
            {
                "title": "جاري ڪيل خلاصو کوليو",
                "body": (
                    "صلاح مشوري جو خلاصو مريض جي پورٽل ۾ تڏهن "
                    "نظر ايندو جڏهن علاج ڪندڙ ڊاڪٽر ان جو جائزو "
                    "وٺي جاري ڪندو. خلاصو پڙهو، آڊيو ٻڌو، تصديق "
                    "ٿيل دوائون ڏسو ۽ PDF ڊائون لوڊ ڪريو."
                ),
            },
            {
                "title": "دوائن جون ياد ڏيارڻيون استعمال ڪريو",
                "body": (
                    "ياد ڏيارڻ جا وقت ڊاڪٽر جي تصديق ٿيل هدايتن "
                    "مان ٺهن ٿا. Taken، Snooze يا Skip استعمال ڪريو. "
                    "غير واضح هدايتن لاءِ سسٽم پاڻمرادو مقرر "
                    "شيڊول نٿو ٺاهي."
                ),
            },
            {
                "title": "آواز واريون ياد ڏيارڻيون",
                "body": (
                    "پورٽل کليل هجي ته آواز واريون ياد ڏيارڻيون "
                    "هلائي سگهجن ٿيون. مريض جي سپورٽ ٿيل ٻولي "
                    "لاءِ موجود آڊيو رستو استعمال ٿيندو."
                ),
            },
            {
                "title": "ٻيهر جائزو گهرو",
                "body": (
                    "جاري ٿيڻ کان پوءِ مريض مجاز cross-check "
                    "ڊاڪٽر کان ٻيهر جائزي جي درخواست ڪري سگهي ٿو."
                ),
            },
        ],
        "faqs": [
            {
                "q": "ڇا MediExplain+ منهنجي تشخيص ڪري ٿو؟",
                "a": (
                    "نه. هي ڊاڪٽر جي جائزي هيٺ هڪ رابطي وارو "
                    "پروٽوٽائپ آهي ۽ پاڻمرادو تشخيص يا نسخو نٿو ڪري."
                ),
            },
            {
                "q": "نئين صلاح مشوري ڇو نظر نٿي اچي؟",
                "a": (
                    "مريض صرف اها صلاح مشوري ڏسي ٿو جيڪا علاج "
                    "ڪندڙ ڊاڪٽر جائزي کان پوءِ جاري ڪئي هجي."
                ),
            },
            {
                "q": "جيڪڏهن ياد ڏيارڻي غلط لڳي ته ڇا ڪجي؟",
                "a": (
                    "ڊاڪٽر جي تصديق ٿيل هدايتن کي ترجيح ڏيو ۽ "
                    "ڪلينيڪل ٽيم سان رابطو ڪريو."
                ),
            },
            {
                "q": "ڇا خلاصو PDF ۾ ملي سگهي ٿو؟",
                "a": "ها. جاري ڪيل صلاح مشوري جو PDF ملي سگهي ٿو.",
            },
        ],
    },

    "ar": {
        "title": "مركز تعلّم المريض",
        "subtitle": (
            "تعلّم كيفية استخدام بوابة MediExplain+ "
            "بأمان وثقة."
        ),
        "guides": [
            {
                "title": "افتح الملخص الصادر",
                "body": (
                    "تظهر الاستشارة في بوابة المريض فقط بعد أن "
                    "يراجعها الطبيب المعالج ويصدرها. يمكنك قراءة "
                    "الملخص والاستماع إلى الصوت وعرض الأدوية "
                    "المؤكدة وتنزيل ملف PDF."
                ),
            },
            {
                "title": "استخدم تذكيرات الأدوية",
                "body": (
                    "تأتي أوقات التذكير من تعليمات الدواء التي "
                    "أكدها الطبيب. استخدم Taken أو Snooze أو Skip. "
                    "لا ينشئ النظام جدولاً ثابتاً من تلقاء نفسه "
                    "عندما تكون التعليمات غير واضحة."
                ),
            },
            {
                "title": "استخدم التذكيرات الصوتية",
                "body": (
                    "يمكن تشغيل التذكيرات الصوتية أثناء فتح "
                    "البوابة، ويُستخدم مسار الصوت المتاح للغة "
                    "المريض المدعومة."
                ),
            },
            {
                "title": "اطلب مراجعة ثانية",
                "body": (
                    "بعد إصدار الاستشارة يمكن للمريض طلب مراجعة "
                    "من طبيب cross-check مخوّل. لا تغيّر هذه "
                    "المراجعة تعليمات الطبيب المعالج تلقائياً."
                ),
            },
        ],
        "faqs": [
            {
                "q": "هل يقوم MediExplain+ بتشخيص حالتي؟",
                "a": (
                    "لا. هو نموذج أولي للتواصل يخضع لمراجعة الطبيب "
                    "ولا يقوم بالتشخيص أو وصف العلاج بشكل مستقل."
                ),
            },
            {
                "q": "لماذا لا أرى الاستشارة الجديدة؟",
                "a": (
                    "لا تظهر الاستشارة للمريض إلا بعد مراجعتها "
                    "وإصدارها من الطبيب المعالج."
                ),
            },
            {
                "q": "ماذا أفعل إذا بدا التذكير غير صحيح؟",
                "a": (
                    "اتبع تعليمات الطبيب المؤكدة واتصل بالفريق "
                    "السريري إذا كان أي شيء غير واضح."
                ),
            },
            {
                "q": "هل يمكنني تنزيل الملخص كملف PDF؟",
                "a": "نعم. يمكن تنزيل PDF للاستشارة التي تم إصدارها.",
            },
        ],
    },
}


@router.get("")
async def learning_content(
    lang: str | None = Query(None),
    user: User = Depends(get_current_user),
):
    requested = (
        lang
        or user.preferred_language
        or "en"
    )

    if requested not in CONTENT:
        requested = "en"

    return {
        "language": requested,
        **CONTENT[requested],
    }
