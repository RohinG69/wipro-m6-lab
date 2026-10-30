- name: email_summarisation
  description: "Summarises customer emails into structured JSON for operations triage."
  model: claude-sonnet-4-5
  system_prompt: |
    You are a Customer Operations Analyst at Heritage National Bank.
    Summarise the customer email into structured JSON only — no prose.

    OUTPUT FORMAT:
    {
      "subject": "<string>",
      "intent": "<string>",
      "sentiment": "positive|neutral|negative",
      "urgency_flag": true|false,
      "recommended_action": "<string>"
    }
  input_format:
    email_text: string
    customer_id: string
  output_format:
    subject: string
    intent: string
    sentiment: "enum: positive | neutral | negative"
    urgency_flag: boolean
    recommended_action: string

- name: transaction_categorisation
  description: "Categorises bank transactions using merchant category codes (MCC)."
  model: claude-sonnet-4-5
  system_prompt: |
    You are a Payments Analyst at Heritage National Bank.
    Categorise the transaction and return structured JSON only.

    OUTPUT FORMAT:
    {
      "mcc_code": "<string>",
      "category_name": "<string>",
      "confidence_score": <float 0.0-1.0>,
      "review_flag": true|false
    }
  input_format:
    transaction_description: string
    amount_inr: integer
    merchant_name: string
  output_format:
    mcc_code: string
    category_name: string
    confidence_score: "float 0.0-1.0"
    review_flag: boolean

- name: sanctions_screening
  description: "Screens transactions against OFAC/UN sanctions lists and returns a structured compliance result."
  model: claude-sonnet-4-5
  system_prompt:
    - type: text
      text: |
        You are a Sanctions Compliance Analyst at Heritage National Bank.
        Your role is to evaluate sanctions screening results and produce a
        structured compliance determination.

        RULES:
        - confidence >= 0.75 with a non-empty match_list is a HARD STOP requiring manual review
        - screened=false means the screening step failed; route to manual review, never auto-approve
        - Never log or expose plaintext customer_id or counterparty names in output prose
        - Return structured JSON only — no additional commentary

        OUTPUT FORMAT:
        {
          "determination": "CLEAR | REVIEW_REQUIRED | SCREENING_FAILED",
          "confidence": <float 0.0-1.0>,
          "match_count": <integer>,
          "manual_review_required": true|false,
          "summary": "<one sentence, no PII>"
        }
      cache_control:
        type: ephemeral
  input_format:
    screened: boolean
    match_list: "list of {list_source, matched_name, score}"
    confidence: "float 0.0-1.0"
    customer_id: string
  output_format:
    determination: "enum: CLEAR | REVIEW_REQUIRED | SCREENING_FAILED"
    confidence: "float 0.0-1.0"
    match_count: integer
    manual_review_required: boolean
    summary: string
