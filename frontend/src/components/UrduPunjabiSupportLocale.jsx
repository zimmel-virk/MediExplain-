import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../api/auth'

/**
 * This component provides Urdu and Shahmukhi Punjabi localisation for the
 * MediExplain+ Support & Safety page. It contains the translated support,
 * privacy, technical-help and reporting text used by patient accounts, applies
 * those translations to visible page text and selected accessibility attributes,
 * watches for dynamically rendered content so new elements are translated as
 * well, and restores the original English text and attributes when the patient
 * leaves the support page or changes language.
 */

const COPY = {
  ur: {
    'SUPPORT · PRIVACY · SAFETY':
      'مدد · رازداری · حفاظت',

    'Support & Safety Centre':
      'مدد اور حفاظت کا مرکز',

    'Report a privacy concern, get help, flag a problem or contact the project team from one place.':
      'رازداری سے متعلق تشویش رپورٹ کریں، مدد حاصل کریں، کسی مسئلے کی اطلاع دیں یا ایک ہی جگہ سے پروجیکٹ ٹیم سے رابطہ کریں۔',

    'Report a privacy concern':
      'رازداری سے متعلق تشویش رپورٹ کریں',

    'Report a technical problem':
      'تکنیکی مسئلہ رپورٹ کریں',

    'Tell us about errors, broken pages, audio issues, reminders or unexpected system behaviour.':
      'غلطیوں، خراب صفحات، آڈیو مسائل، یاددہانیوں یا غیر متوقع سسٹم رویے کے بارے میں ہمیں بتائیں۔',

    'Get help':
      'مدد حاصل کریں',

    'Ask for help using your dashboard, patient portal, assistant review or reminder features.':
      'اپنے ڈیش بورڈ، مریض پورٹل یا یاددہانی کی خصوصیات استعمال کرنے میں مدد حاصل کریں۔',

    'Contact project team':
      'پروجیکٹ ٹیم سے رابطہ کریں',

    'Contact us':
      'ہم سے رابطہ کریں',

    'Privacy concern':
      'رازداری سے متعلق تشویش',

    'Technical problem':
      'تکنیکی مسئلہ',

    'Help request':
      'مدد کی درخواست',

    'Category':
      'قسم',

    'Urgency':
      'اہمیت',

    'Details':
      'تفصیلات',

    'Message':
      'پیغام',

    'Subject':
      'موضوع',

    'Email':
      'ای میل',

    'Your email':
      'آپ کا ای میل',

    'Describe what happened':
      'بتائیں کیا ہوا',

    'Describe your concern':
      'اپنی تشویش کی تفصیل لکھیں',

    'How can we help?':
      'ہم آپ کی کس طرح مدد کر سکتے ہیں؟',

    'Send':
      'بھیجیں',

    'Send message':
      'پیغام بھیجیں',

    'Submit':
      'جمع کریں',

    'Submit report':
      'رپورٹ جمع کریں',

    'Report issue':
      'مسئلہ رپورٹ کریں',

    'Your reports':
      'آپ کی رپورٹس',

    'Recent reports':
      'حالیہ رپورٹس',

    'Normal':
      'معمول',

    'Urgent':
      'فوری',

    'High':
      'زیادہ',

    'Low':
      'کم',

    'normal':
      'معمول',

    'urgent':
      'فوری',

    'Submitted':
      'جمع ہو گئی',

    'Open':
      'کھلا',

    'Resolved':
      'حل ہو گیا',

    'Thank you. Your report has been submitted.':
      'شکریہ۔ آپ کی رپورٹ جمع کر دی گئی ہے۔',

    'No reports yet.':
      'ابھی کوئی رپورٹ موجود نہیں۔'
  },


  pa_shah: {
    'SUPPORT · PRIVACY · SAFETY':
      'مدد · رازداری · حفاظت',

    'Support & Safety Centre':
      'مدد تے حفاظت دا مرکز',

    'Report a privacy concern, get help, flag a problem or contact the project team from one place.':
      'رازداری دی تشویش رپورٹ کرو، مدد لو، مسئلہ دسو یا اکّو جگہ توں پروجیکٹ ٹیم نال رابطہ کرو۔',

    'Report a privacy concern':
      'رازداری دی تشویش رپورٹ کرو',

    'Report a technical problem':
      'تکنیکی مسئلہ رپورٹ کرو',

    'Tell us about errors, broken pages, audio issues, reminders or unexpected system behaviour.':
      'غلطیاں، خراب صفحے، آڈیو مسئلے، یاددہانیاں یا غیر متوقع سسٹم رویے بارے سانوں دسو۔',

    'Get help':
      'مدد لو',

    'Ask for help using your dashboard, patient portal, assistant review or reminder features.':
      'اپنا ڈیش بورڈ، مریض پورٹل یا یاددہانی فیچر ورتن لئی مدد لو۔',

    'Contact project team':
      'پروجیکٹ ٹیم نال رابطہ کرو',

    'Contact us':
      'ساڈے نال رابطہ کرو',

    'Privacy concern':
      'رازداری دی تشویش',

    'Technical problem':
      'تکنیکی مسئلہ',

    'Help request':
      'مدد دی درخواست',

    'Category':
      'قسم',

    'Urgency':
      'اہمیت',

    'Details':
      'تفصیل',

    'Message':
      'پیغام',

    'Subject':
      'موضوع',

    'Email':
      'ای میل',

    'Your email':
      'تہاڈا ای میل',

    'Describe what happened':
      'دسو کی ہویا',

    'Describe your concern':
      'اپنی تشویش دی تفصیل لکھو',

    'How can we help?':
      'اسی تہاڈی کیویں مدد کر سکدے آں؟',

    'Send':
      'بھیجو',

    'Send message':
      'پیغام بھیجو',

    'Submit':
      'جمع کرو',

    'Submit report':
      'رپورٹ جمع کرو',

    'Report issue':
      'مسئلہ رپورٹ کرو',

    'Your reports':
      'تہاڈیاں رپورٹس',

    'Recent reports':
      'حالیہ رپورٹس',

    'Normal':
      'عام',

    'Urgent':
      'فوری',

    'High':
      'زیادہ',

    'Low':
      'گھٹ',

    'normal':
      'عام',

    'urgent':
      'فوری',

    'Submitted':
      'جمع ہو گئی',

    'Open':
      'کھلا',

    'Resolved':
      'حل ہو گیا',

    'Thank you. Your report has been submitted.':
      'شکریہ۔ تہاڈی رپورٹ جمع ہو گئی اے۔',

    'No reports yet.':
      'ہن تک کوئی رپورٹ نئیں۔'
  }
}


function clean(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, ' ')
}


export default function UrduPunjabiSupportLocale() {
  const { user } = useAuth()
  const location = useLocation()

  useEffect(() => {
    if (
      user?.role !== 'patient'
      || !COPY[user?.preferred_language]
      || location.pathname !== '/support'
    ) {
      return undefined
    }

    const table =
      COPY[user.preferred_language]

    const root =
      document.querySelector('main.page')

    if (!root) {
      return undefined
    }

    const originalText =
      new Map()

    const originalAttributes =
      []

    function translateText(node) {
      if (
        !node
        || node.nodeType !== Node.TEXT_NODE
      ) {
        return
      }

      const key =
        clean(node.nodeValue)

      if (!key || !table[key]) {
        return
      }

      if (!originalText.has(node)) {
        originalText.set(
          node,
          node.nodeValue
        )
      }

      const before =
        node.nodeValue.match(/^\s*/)?.[0]
        || ''

      const after =
        node.nodeValue.match(/\s*$/)?.[0]
        || ''

      node.nodeValue =
        before
        + table[key]
        + after
    }

    function translateAttributes(element) {
      if (
        !element
        || element.nodeType
        !== Node.ELEMENT_NODE
      ) {
        return
      }

      for (
        const attr
        of [
          'placeholder',
          'title',
          'aria-label',
        ]
      ) {
        if (
          !element.hasAttribute(attr)
        ) {
          continue
        }

        const raw =
          element.getAttribute(attr)

        const key =
          clean(raw)

        if (!table[key]) {
          continue
        }

        originalAttributes.push([
          element,
          attr,
          raw,
        ])

        element.setAttribute(
          attr,
          table[key]
        )
      }
    }

    function apply(target) {
      if (!target) {
        return
      }

      if (
        target.nodeType
        === Node.TEXT_NODE
      ) {
        translateText(target)
        return
      }

      if (
        target.nodeType
        !== Node.ELEMENT_NODE
        && target.nodeType
        !== Node.DOCUMENT_FRAGMENT_NODE
      ) {
        return
      }

      if (
        target.nodeType
        === Node.ELEMENT_NODE
      ) {
        translateAttributes(target)
      }

      const walker =
        document.createTreeWalker(
          target,
          NodeFilter.SHOW_TEXT
        )

      let node

      while (
        (
          node =
            walker.nextNode()
        )
      ) {
        translateText(node)
      }

      if (target.querySelectorAll) {
        target
          .querySelectorAll(
            '[placeholder],'
            + '[title],'
            + '[aria-label]'
          )
          .forEach(
            translateAttributes
          )
      }
    }

    apply(root)

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
              translateText(
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
      root,
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
        of originalText
      ) {
        if (node?.isConnected) {
          node.nodeValue =
            original
        }
      }

      for (
        const [
          element,
          attr,
          original,
        ]
        of originalAttributes
      ) {
        if (element?.isConnected) {
          element.setAttribute(
            attr,
            original
          )
        }
      }
    }
  }, [
    user?.role,
    user?.preferred_language,
    location.pathname,
  ])

  return null
}
