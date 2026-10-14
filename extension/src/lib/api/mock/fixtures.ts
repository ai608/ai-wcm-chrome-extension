import type {
  ContactContext,
  ContactHistory,
  PersonalizedScript,
  ScriptDefinition,
} from '@/lib/api/types'

export const MOCK_LOCATION_ID = 'MOCK_LOCATION'

export const scriptDefinition: ScriptDefinition = {
  version: 3,
  sections: [
    {
      id: 'opener',
      title: 'Opener',
      defaultOpen: true,
      blocks: [
        {
          type: 'say',
          id: 'opener-line',
          tone: 'highlight',
          text: 'Hey {{contact.first_name}}, this is {{caller.first_name}} with WCM. {{ai.opener}}',
        },
        {
          type: 'response',
          id: 'r-looking',
          label: 'YES, LOOKING FOR MORE PATIENTS',
          text: 'Great — that is exactly what we do for clinics like {{contact.company_name}}. {{ai.hook}}',
        },
        {
          type: 'response',
          id: 'r-capacity',
          label: 'AT CAPACITY / TOO BUSY',
          text: 'Totally fair. Most of our best clients said the same before they added {{field.contact.goal_new_patients}} new patients a month on autopilot.',
        },
        {
          type: 'response',
          id: 'r-what',
          label: 'WHAT DO YOU DO?',
          text: 'We run patient-acquisition ads and follow-up for wellness clinics — med spas, IV therapy, weight loss, HRT and chiropractic. {{ai.hook}}',
        },
        {
          type: 'response',
          id: 'r-leads',
          label: 'DO YOU SELL LEADS?',
          text: 'No — we never sell shared leads. Everything we generate for {{contact.company_name}} is exclusive to you.',
        },
        {
          type: 'response',
          id: 'r-timing',
          label: 'NOT INTERESTED – TIMING',
          text: 'Understood. When would be a better time — is it a budget cycle thing or just a busy season in {{contact.city}}?',
        },
        {
          type: 'response',
          id: 'r-firm',
          label: 'NOT INTERESTED – FIRM',
          text: 'No problem, I will not take more of your time. Thanks {{contact.first_name}}.',
        },
      ],
    },
    {
      id: 'qualification',
      title: 'Qualification',
      defaultOpen: true,
      blocks: [
        {
          type: 'say',
          id: 'qual-line',
          text: 'Quick question so I point you to the right next step — {{ai.qualifier}}',
        },
        { type: 'tip', id: 'qual-tip', text: "Don't say SEO or ads — lead with patient bookings." },
        {
          type: 'response',
          id: 'q-owner',
          label: 'OWNER DOES IT',
          text: 'Got it — so it lives on your plate on top of running {{contact.company_name}}. How many hours a week does that eat up?',
        },
        {
          type: 'response',
          id: 'q-happy',
          label: 'AGENCY – HAPPY',
          text: 'Great, glad that is working. Are they driving actual booked appointments or mostly likes and clicks?',
        },
        {
          type: 'response',
          id: 'q-frustrated',
          label: 'AGENCY – FRUSTRATED',
          text: 'You are not alone — that is the number one reason clinics switch to us. What is the most frustrating part?',
        },
        {
          type: 'response',
          id: 'q-nobody',
          label: 'NOBODY',
          text: 'So growth is all word of mouth right now. How many new patients are you getting a month?',
        },
      ],
    },
    {
      id: 'discovery',
      title: 'Discovery',
      defaultOpen: true,
      blocks: [
        {
          type: 'question',
          id: 'qq-practice-type',
          fieldKey: 'contact.what_type_of_medical_practice_this_is',
          label: 'What type of practice is this?',
          input: 'select',
          options: [
            { value: 'med_spa', label: 'Med Spa' },
            { value: 'iv_therapy', label: 'IV Therapy' },
            { value: 'weight_loss', label: 'Weight Loss / GLP-1' },
            { value: 'hrt', label: 'HRT / Hormone Clinic' },
            { value: 'chiro', label: 'Chiropractic' },
            { value: 'functional', label: 'Functional Medicine' },
          ],
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-procedures',
          fieldKey: 'contact.procedures_offer',
          label: 'Which procedures do you offer?',
          input: 'checkbox_group',
          options: [
            { value: 'botox', label: 'Botox / Neurotoxins' },
            { value: 'fillers', label: 'Dermal Fillers' },
            { value: 'laser', label: 'Laser Hair Removal' },
            { value: 'iv', label: 'IV Therapy' },
            { value: 'glp1', label: 'Medical Weight Loss (GLP-1)' },
            { value: 'hrt', label: 'Hormone Replacement (HRT)' },
            { value: 'microneedling', label: 'Microneedling' },
            { value: 'chiro', label: 'Chiropractic' },
            { value: 'functional', label: 'Functional Medicine' },
          ],
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-locations',
          fieldKey: 'contact.how_many_locations_do_you_have',
          label: 'How many locations do you have?',
          input: 'number',
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-new-patients',
          fieldKey: 'contact.monthly_new_patients',
          label: 'How many new patients per month today?',
          input: 'number',
          requiredForBooking: true,
        },
        {
          type: 'question',
          id: 'qq-patient-value',
          fieldKey: 'contact.avg_patient_value',
          label: 'Average patient value ($)?',
          help: 'First-visit revenue plus typical upsell.',
          input: 'currency',
          requiredForBooking: true,
        },
        {
          type: 'question',
          id: 'qq-goal',
          fieldKey: 'contact.goal_new_patients',
          label: 'Goal: new patients per month?',
          input: 'number',
          requiredForBooking: true,
        },
        {
          type: 'question',
          id: 'qq-sources',
          fieldKey: 'contact.patient_sources',
          label: 'Where do patients come from today?',
          input: 'checkbox_group',
          options: [
            { value: 'referrals', label: 'Referrals' },
            { value: 'google_ads', label: 'Google Ads' },
            { value: 'meta_ads', label: 'Meta Ads' },
            { value: 'organic_social', label: 'Instagram / TikTok organic' },
            { value: 'groupon', label: 'Groupon' },
            { value: 'seo', label: 'SEO' },
            { value: 'walkins', label: 'Walk-ins' },
          ],
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-spend',
          fieldKey: 'contact.monthly_marketing_spend',
          label: 'Monthly marketing spend?',
          input: 'select',
          options: [
            { value: '0', label: '$0' },
            { value: '1-2k', label: '$1k – $2k' },
            { value: '2-5k', label: '$2k – $5k' },
            { value: '5k-plus', label: '$5k+' },
          ],
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-contact-method',
          fieldKey: 'contact.preferred_contact_method',
          label: 'Best way to reach them?',
          input: 'radio',
          options: [
            { value: 'phone', label: 'Phone' },
            { value: 'text', label: 'Text' },
            { value: 'email', label: 'Email' },
          ],
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-decision-maker',
          fieldKey: 'contact.decision_maker_name',
          label: 'Decision maker name?',
          input: 'text',
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-why',
          fieldKey: 'contact.their_why',
          label: 'Their why — why grow now?',
          input: 'textarea',
          requiredForBooking: false,
        },
        {
          type: 'question',
          id: 'qq-revenue',
          fieldKey: 'contact.annual_revenue',
          label: 'Annual revenue ($)?',
          input: 'currency',
          requiredForBooking: false,
        },
      ],
    },
    {
      id: 'confirm',
      title: 'Confirm / Booking',
      defaultOpen: false,
      blocks: [
        {
          type: 'recap',
          id: 'recap-main',
          rows: [
            { label: 'Clinic', source: 'contact', key: 'company_name' },
            { label: 'City', source: 'contact', key: 'city' },
            {
              label: 'New patients / mo',
              source: 'field',
              fieldKey: 'contact.monthly_new_patients',
            },
            { label: 'Avg patient value', source: 'field', fieldKey: 'contact.avg_patient_value' },
            {
              label: 'Goal new patients / mo',
              source: 'field',
              fieldKey: 'contact.goal_new_patients',
            },
            {
              label: 'Current revenue',
              source: 'computed',
              key: 'current_revenue',
              formula: {
                op: 'multiply',
                fields: ['contact.monthly_new_patients', 'contact.avg_patient_value'],
              },
            },
            {
              label: 'Target revenue',
              source: 'computed',
              key: 'target_revenue',
              formula: {
                op: 'multiply',
                fields: ['contact.goal_new_patients', 'contact.avg_patient_value'],
              },
            },
          ],
          sayItBack:
            'So just to confirm — {{contact.company_name}} is doing {{field.contact.monthly_new_patients}} new patients a month at {{field.contact.avg_patient_value}} each, so about {{computed.current_revenue}} a month, and you want to get to {{field.contact.goal_new_patients}} new patients, which is {{computed.target_revenue}}. Did I get that right?',
        },
        {
          type: 'say',
          id: 'confirm-next',
          text: 'If that sounds right, the next step is a 20-minute Zoom where we map exactly how we would fill that gap for {{contact.company_name}}. {{ai.booking_push}}',
        },
        {
          type: 'tip',
          id: 'refuse-tip',
          text: 'If they refuse Zoom: offer the audit report instead, then book a callback — never just hang up.',
        },
        { type: 'booking', id: 'booking-widget' },
      ],
    },
    {
      id: 'outcome',
      title: 'Outcome',
      defaultOpen: false,
      blocks: [
        {
          type: 'outcome',
          id: 'outcome-main',
          outcomes: [
            { id: 'schedule_appointment', label: 'Schedule Appointment', books: true },
            { id: 'callback_requested', label: 'Callback Requested', books: false },
            { id: 'send_audit', label: 'Send Audit Report', books: false },
            { id: 'nurture', label: 'Interested – Nurture', books: false },
            { id: 'not_interested_timing', label: 'Not Interested – Timing', books: false },
            { id: 'not_interested_firm', label: 'Not Interested – Firm', books: false },
            { id: 'has_agency', label: 'Has Agency / Under Contract', books: false },
            { id: 'not_a_fit', label: 'Not a Fit', books: false },
            { id: 'gatekeeper', label: 'Gatekeeper – DM Unavailable', books: false },
          ],
        },
      ],
    },
    {
      id: 'faq',
      title: 'FAQ & Objections',
      defaultOpen: false,
      blocks: [
        {
          type: 'faq',
          id: 'faq-main',
          items: [
            {
              q: 'What do you do?',
              a: 'We run Meta and Google ads plus automated follow-up that turn clicks into booked appointments for wellness clinics. You only talk to patients who already booked.',
            },
            {
              q: 'Do you guarantee patients?',
              a: 'No agency can ethically guarantee patients. We guarantee the system: targeted ads, same-day follow-up, and a show-up process — and we track cost per booked appointment with you weekly.',
            },
            {
              q: 'We already have an agency',
              a: 'Great — are they booking you measurable appointments each month, or reporting clicks? We can run a free audit against what they do so you can compare apples to apples.',
            },
            {
              q: 'Just send me an email',
              a: 'Happy to — what would be most useful, the audit of {{contact.company_name}} or client results? And what is the best email?',
            },
            {
              q: 'Can we do a phone call instead of Zoom?',
              a: 'We can, but Zoom lets us screen-share your numbers and the plan — it is 20 minutes and most owners find it 10x more useful. Morning or afternoon better?',
            },
            {
              q: 'How did you get my info?',
              a: 'Your clinic is listed publicly in {{contact.city}} and caught our eye because {{ai.opener}} Happy to remove you if you prefer.',
            },
          ],
        },
      ],
    },
    {
      id: 'do-not-book',
      title: 'Do Not Book',
      defaultOpen: false,
      blocks: [
        {
          type: 'do_not_book',
          id: 'dnb-main',
          items: [
            'Wants to buy leads only, not a marketing partner',
            'Happy and locked in with current vendor long-term',
            "Won't share basic business info (patients, revenue, goals)",
            'Brand-new clinic with no patients, website or Google profile yet',
          ],
        },
      ],
    },
    {
      id: 'other',
      title: 'Other Saved Fields',
      defaultOpen: false,
      blocks: [
        {
          type: 'question',
          id: 'qq-website',
          fieldKey: 'contact.website_url',
          label: 'Website URL?',
          input: 'text',
          requiredForBooking: false,
        },
      ],
    },
  ],
}

interface MockContactState {
  context: ContactContext
  script: PersonalizedScript
  history: ContactHistory
  scriptReadyAt: number | null
  enrichReadyAt: number | null
}

function glowContext(): ContactContext {
  return {
    contact: {
      id: 'c_glow',
      firstName: 'Maya',
      lastName: 'Reyes',
      companyName: 'Glow Aesthetics Med Spa',
      email: 'maya@glowaesthetics.example.com',
      phone: '+15125550134',
      city: 'Austin',
      state: 'TX',
      postalCode: '78704',
      website: 'https://glowaesthetics.example.com',
      tags: ['med_spa', 'hot_lead'],
    },
    fieldValues: {
      'contact.what_type_of_medical_practice_this_is': 'med_spa',
      'contact.procedures_offer': ['botox', 'fillers', 'iv'],
      'contact.how_many_locations_do_you_have': 1,
      'contact.monthly_new_patients': 40,
      'contact.avg_patient_value': 350,
      'contact.goal_new_patients': null,
      'contact.patient_sources': ['referrals', 'organic_social'],
      'contact.monthly_marketing_spend': '1-2k',
      'contact.their_why': 'Open a second room by summer.',
    },
    enrichment: {
      status: 'enriched',
      services: ['Botox', 'Fillers', 'IV Therapy', 'Medical Weight Loss'],
      googleRating: 4.7,
      googleReviewCount: 212,
      score: 82,
      updatedAt: '2026-10-10T15:00:00Z',
    },
  }
}

function vitalContext(): ContactContext {
  return {
    contact: {
      id: 'c_vital',
      firstName: 'Marcus',
      lastName: 'Bell',
      companyName: 'Vital IV Lounge',
      email: 'marcus@vitaliv.example.com',
      phone: '+13055550198',
      city: 'Miami',
      state: 'FL',
      postalCode: '33139',
      website: 'https://vitaliv.example.com',
      tags: ['iv_therapy'],
    },
    fieldValues: {},
    enrichment: {
      status: 'not_enriched',
      services: [],
      googleRating: null,
      googleReviewCount: null,
      score: null,
      updatedAt: null,
    },
  }
}

function peakContext(): ContactContext {
  return {
    contact: {
      id: 'c_peak',
      firstName: 'Sarah',
      lastName: 'Lindqvist',
      companyName: 'Peak Chiropractic & Wellness',
      email: 'sarah@peakchiro.example.com',
      phone: '+13035550177',
      city: 'Denver',
      state: 'CO',
      postalCode: '80202',
      website: 'https://peakchiro.example.com',
      tags: ['chiropractic'],
    },
    fieldValues: {
      'contact.what_type_of_medical_practice_this_is': 'chiro',
      'contact.how_many_locations_do_you_have': 2,
    },
    enrichment: {
      status: 'enriched',
      services: ['Chiropractic', 'Functional Medicine'],
      googleRating: 4.9,
      googleReviewCount: 341,
      score: 88,
      updatedAt: '2026-10-11T12:00:00Z',
    },
  }
}

function failContext(): ContactContext {
  return {
    contact: {
      id: 'c_fail',
      firstName: 'Dana',
      lastName: 'Whitfield',
      companyName: 'Pure Glow Studio',
      email: 'dana@pureglow.example.com',
      phone: '+16025550142',
      city: 'Phoenix',
      state: 'AZ',
      postalCode: '85004',
      website: 'https://pureglow.example.com',
      tags: [],
    },
    fieldValues: {
      'contact.monthly_new_patients': 25,
      'contact.avg_patient_value': 275,
    },
    enrichment: {
      status: 'enriched',
      services: ['Microneedling', 'Laser Hair Removal'],
      googleRating: 4.5,
      googleReviewCount: 98,
      score: 71,
      updatedAt: '2026-10-09T09:00:00Z',
    },
  }
}

const glowSlots = {
  opener:
    'I saw your 4.7-star reviews keep mentioning same-week appointments — most med spas in Austin cannot say that.',
  hook: 'Clinics your size usually add 20–30 booked consults a month once follow-up is automatic.',
  qualifier: 'are you doing your own marketing, or is someone helping you?',
  objection_hint: 'If price comes up, anchor on one extra Botox patient covering the month.',
  booking_push: 'We have two audit slots left this week — want me to grab one for you?',
}

export const initialStates: Record<string, MockContactState> = {
  c_glow: {
    context: glowContext(),
    script: {
      status: 'ready',
      scriptVersion: 3,
      generatedAt: '2026-10-13T16:00:00Z',
      slots: glowSlots,
      error: null,
    },
    history: {
      brief: {
        text: 'Glow Aesthetics is a single-location med spa in Austin doing ~40 new patients/mo at ~$350 value. Owner-run marketing, spending $1–2k. Wants a second treatment room by summer. Last call: asked for pricing, went quiet for 3 weeks.',
        generatedAt: '2026-10-13T16:05:00Z',
      },
      activities: [
        {
          id: 'a1',
          kind: 'call',
          source: 'Sam Rivera',
          createdAt: '2026-09-19T14:07:00Z',
          body: 'Connected with Maya. She asked for pricing over email, said she would review with her husband.\nFollow up in 2 weeks.',
        },
        {
          id: 'a2',
          kind: 'note',
          source: 'Automation',
          createdAt: '2026-09-26T09:00:00Z',
          body: 'Lead score updated to 82 after enrichment refresh.\nhttps://glowaesthetics.example.com',
        },
        {
          id: 'a3',
          kind: 'sms',
          source: 'Sam Rivera',
          createdAt: '2026-10-02T11:32:00Z',
          body: 'Sent pricing + 2 case studies. Maya replied "looking it over".',
        },
        {
          id: 'a4',
          kind: 'email',
          source: 'Automation',
          createdAt: '2026-10-08T08:15:00Z',
          body: 'Re-engagement email opened 3 times.',
        },
      ],
      opportunities: [
        {
          id: 'o1',
          name: 'Glow Aesthetics — Growth Plan',
          monetaryValue: 24000,
          status: 'open',
          pipelineName: 'WCM Sales',
          stageName: 'Discovery Call',
        },
      ],
      lastContactedAt: '2026-10-08T08:15:00Z',
    },
    scriptReadyAt: null,
    enrichReadyAt: null,
  },
  c_vital: {
    context: vitalContext(),
    script: { status: 'none', scriptVersion: 3, generatedAt: null, slots: {}, error: null },
    history: {
      brief: null,
      activities: [],
      opportunities: [],
      lastContactedAt: null,
    },
    scriptReadyAt: null,
    enrichReadyAt: null,
  },
  c_peak: {
    context: peakContext(),
    script: { status: 'generating', scriptVersion: 3, generatedAt: null, slots: {}, error: null },
    history: {
      brief: null,
      activities: [
        {
          id: 'a1',
          kind: 'call',
          source: 'Priya Nair',
          createdAt: '2026-08-23T21:07:00Z',
          body: 'Left voicemail for Sarah. Front desk said she is with patients until 5.',
        },
        {
          id: 'a2',
          kind: 'note',
          source: 'Automation',
          createdAt: '2026-08-24T09:00:00Z',
          body: 'Imported from list purchase. Enriched automatically.',
        },
      ],
      opportunities: [
        {
          id: 'o1',
          name: 'Peak Chiropractic — Pilot',
          monetaryValue: 18000,
          status: 'abandoned',
          pipelineName: 'WCM Sales',
          stageName: 'No Show',
        },
      ],
      lastContactedAt: '2026-08-23T21:07:00Z',
    },
    scriptReadyAt: Date.now() + 5000,
    enrichReadyAt: null,
  },
  c_fail: {
    context: failContext(),
    script: {
      status: 'failed',
      scriptVersion: 3,
      generatedAt: null,
      slots: {},
      error: 'Model timeout',
    },
    history: {
      brief: {
        text: 'Pure Glow Studio in Phoenix. Small team, owner does everything. Early-stage data.',
        generatedAt: '2026-10-12T10:00:00Z',
      },
      activities: [
        {
          id: 'a1',
          kind: 'note',
          source: 'Automation',
          createdAt: '2026-10-12T10:00:00Z',
          body: 'Created from inbound form.',
        },
      ],
      opportunities: [],
      lastContactedAt: null,
    },
    scriptReadyAt: null,
    enrichReadyAt: null,
  },
}

export function cloneState(id: string): MockContactState {
  return structuredClone(initialStates[id]) as MockContactState
}

export function vitalEnrichedContext(): ContactContext {
  const ctx = vitalContext()
  ctx.enrichment = {
    status: 'enriched',
    services: ['IV Therapy', 'Medical Weight Loss'],
    googleRating: 4.6,
    googleReviewCount: 154,
    score: 79,
    updatedAt: new Date().toISOString(),
  }
  return ctx
}

export const vitalSlots = {
  opener:
    'Vital IV is one of the few lounges on South Beach pushing GLP-1 support alongside drips — that combo is converting well right now.',
  hook: 'IV lounges running weekend promos with us usually see 15–25 extra bookings a month.',
  qualifier: 'is marketing on you, or do you have someone running it?',
  objection_hint: 'If they say summer is slow, pitch the tourist-season ramp plan.',
  booking_push: 'Want me to hold a 20-minute slot so you can see the exact promo we would run?',
}

export function fieldLabel(key: string): string {
  return key.replace(/^contact\./, '').replace(/_/g, ' ')
}
