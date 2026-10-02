-- Prepza local PostgreSQL schema baseline
-- Generated from the live Supabase public schema on 2026-10-02.
-- SCHEMA ONLY: no production rows are included.
-- This is a local bootstrap snapshot, not a production migration.
-- Production RLS/auth/storage policies are intentionally not included.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Sequences
CREATE SEQUENCE IF NOT EXISTS public.ada_request_usage_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ai_answer_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ai_economics_change_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ai_generation_artifact_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ai_generation_subscriber_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ai_job_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ai_usage_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ambassador_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ambassador_payout_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.announcement_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.audit_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.auth_otp_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.b2b_audit_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.b2b_campaign_funding_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.b2b_campaign_ledger_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.b2b_invoice_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.b2b_payment_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.b2b_placement_config_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.b2b_pricing_config_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.concept_prerequisite_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.content_item_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.content_report_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.conversation_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.conversation_key_envelope_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.conversation_participant_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.discovery_campaign_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.discovery_event_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.discovery_push_delivery_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.document_content_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.document_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.flashcard_session_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.follow_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.follow_request_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.forum_post_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.forum_reply_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.generated_material_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.group_file_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.group_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.group_member_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.group_post_comment_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.group_post_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.group_post_like_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.group_question_vote_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.kokoro_gpu_scaling_decisions_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.kokoro_gpu_workers_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.learning_concept_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.learning_event_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.library_publication_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.library_report_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.message_attachment_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.message_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.notification_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.notification_preference_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.opportunity_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.opportunity_promotion_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.opportunity_view_event_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.organisation_billing_event_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.organisation_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.organisation_invoice_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.organisation_kyc_document_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.organisation_member_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.organisation_usage_invoice_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.payment_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.program_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.push_subscription_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.quiz_attempt_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.referral_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.saved_library_material_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.saved_opportunity_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.student_concept_mastery_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.student_entitlement_usage_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.student_learning_profile_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.student_opportunity_discovery_audit_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.student_order_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.student_refund_request_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.student_subscription_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.study_activity_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.study_streak_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.study_time_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.system_setting_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.tutor_conversation_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.tutor_message_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.university_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.user_achievement_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.user_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.user_key_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.user_warning_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.view_progress_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.xp_event_id_seq;

-- Enum types


-- Tables and non-FK constraints
CREATE TABLE public.ada_request_usage (\n    id bigint DEFAULT nextval('ada_request_usage_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    plan_code character varying(20) NOT NULL,
    model character varying(100) NOT NULL,
    provider character varying(40),
    input_tokens integer DEFAULT 0 NOT NULL,
    cached_tokens integer DEFAULT 0 NOT NULL,
    cache_write_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    ada_units bigint DEFAULT 0 NOT NULL,
    cost_usd numeric(14,8) DEFAULT 0 NOT NULL,
    request_key character varying(120),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ada_request_usage_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.ada_usage_day (\n    user_id integer NOT NULL,
    usage_date date NOT NULL,
    ada_units bigint DEFAULT 0 NOT NULL,
    requests integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ada_usage_day_pkey PRIMARY KEY (user_id, usage_date)\n);

CREATE TABLE public.ada_usage_month (\n    user_id integer NOT NULL,
    period_start date NOT NULL,
    ada_units bigint DEFAULT 0 NOT NULL,
    requests integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ada_usage_month_pkey PRIMARY KEY (user_id, period_start)\n);

CREATE TABLE public.ai_answer (\n    id integer DEFAULT nextval('ai_answer_id_seq'::regclass) NOT NULL,
    question_text text NOT NULL,
    answer_text text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, question_text)) STORED,
    model_used character varying(64) NOT NULL,
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    cache_read_tokens integer DEFAULT 0 NOT NULL,
    cache_creation_tokens integer DEFAULT 0 NOT NULL,
    cost_usd numeric(10,6) DEFAULT 0 NOT NULL,
    reuse_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT ai_answer_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.ai_economics_change_log (\n    id bigint DEFAULT nextval('ai_economics_change_log_id_seq'::regclass) NOT NULL,
    admin_user_id integer NOT NULL,
    plan_code character varying(20) NOT NULL,
    changes jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ai_economics_change_log_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.ai_generation_artifact (\n    id bigint DEFAULT nextval('ai_generation_artifact_id_seq'::regclass) NOT NULL,
    fingerprint character varying(128) NOT NULL,
    content_hash character varying(128) NOT NULL,
    feature character varying(40) NOT NULL,
    parameters jsonb DEFAULT '{}'::jsonb NOT NULL,
    prompt_version character varying(80) NOT NULL,
    schema_version character varying(80) NOT NULL,
    scope character varying(20) DEFAULT 'shared'::character varying NOT NULL,
    owner_user_id integer,
    status character varying(20) DEFAULT 'generating'::character varying NOT NULL,
    payload jsonb,
    error_message character varying(4000),
    lease_token character varying(128),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp without time zone,
    CONSTRAINT ai_generation_artifact_fingerprint_key UNIQUE (fingerprint),
    CONSTRAINT ai_generation_artifact_pkey PRIMARY KEY (id),
    CONSTRAINT ck_ai_generation_artifact_scope CHECK (((scope)::text = ANY ((ARRAY['shared'::character varying, 'private'::character varying])::text[]))),
    CONSTRAINT ck_ai_generation_artifact_scope_owner CHECK (((((scope)::text = 'shared'::text) AND (owner_user_id IS NULL)) OR (((scope)::text = 'private'::text) AND (owner_user_id IS NOT NULL))))\n);

CREATE TABLE public.ai_generation_inflight (\n    base_fingerprint character varying(128) NOT NULL,
    artifact_id bigint,
    status character varying(20) DEFAULT 'generating'::character varying NOT NULL,
    lease_token character varying(128),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ai_generation_inflight_pkey PRIMARY KEY (base_fingerprint)\n);

CREATE TABLE public.ai_generation_subscriber (\n    id bigint DEFAULT nextval('ai_generation_subscriber_id_seq'::regclass) NOT NULL,
    base_fingerprint character varying(128) NOT NULL,
    user_id integer NOT NULL,
    status character varying(20) DEFAULT 'waiting'::character varying NOT NULL,
    artifact_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp without time zone,
    CONSTRAINT ai_generation_subscriber_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.ai_generation_variant_access (\n    user_id integer NOT NULL,
    base_fingerprint character varying(64) NOT NULL,
    variant smallint NOT NULL,
    artifact_id bigint,
    status character varying(20) DEFAULT 'reserved'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ai_generation_variant_access_pkey PRIMARY KEY (user_id, base_fingerprint, variant)\n);

CREATE TABLE public.ai_generation_variant_family (\n    base_fingerprint character varying(64) NOT NULL,
    feature character varying(40) NOT NULL,
    base_parameters jsonb DEFAULT '{}'::jsonb NOT NULL,
    next_variant smallint DEFAULT 1 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ai_generation_variant_family_pkey PRIMARY KEY (base_fingerprint)\n);

CREATE TABLE public.ai_job (\n    id integer DEFAULT nextval('ai_job_id_seq'::regclass) NOT NULL,
    document_content_id integer NOT NULL,
    feature character varying(30) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    error_message character varying(500),
    retry_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    batch_id character varying(100),
    notification_id integer,
    progress_percent integer DEFAULT 0 NOT NULL,
    progress_stage character varying(80),
    material_id integer,
    claimed_worker_id character varying(64),
    CONSTRAINT ai_job_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.ai_usage_log (\n    id integer DEFAULT nextval('ai_usage_log_id_seq'::regclass) NOT NULL,
    user_id integer,
    forum_reply_id integer,
    request_type character varying(20) NOT NULL,
    model character varying(64),
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    cache_read_tokens integer DEFAULT 0 NOT NULL,
    cache_creation_tokens integer DEFAULT 0 NOT NULL,
    cost_usd numeric(10,6) DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    provider character varying(20),
    CONSTRAINT ai_usage_log_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.ambassador (\n    id integer DEFAULT nextval('ambassador_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    referral_code character varying(20) NOT NULL,
    status character varying(20) NOT NULL,
    applied_at timestamp without time zone,
    reviewed_by integer,
    reviewed_at timestamp without time zone,
    rejection_reason character varying(500),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    CONSTRAINT ambassador_pkey PRIMARY KEY (id),
    CONSTRAINT ambassador_referral_code_key UNIQUE (referral_code),
    CONSTRAINT ambassador_user_id_key UNIQUE (user_id)\n);

CREATE TABLE public.ambassador_payout (\n    id integer DEFAULT nextval('ambassador_payout_id_seq'::regclass) NOT NULL,
    ambassador_id integer NOT NULL,
    amount integer NOT NULL,
    status character varying(20) NOT NULL,
    payout_destination character varying(20) NOT NULL,
    paystack_transfer_code character varying(100),
    requested_at timestamp without time zone,
    reviewed_by integer,
    reviewed_at timestamp without time zone,
    rejection_reason character varying(500),
    paid_at timestamp without time zone,
    recipient_first_name character varying(100) NOT NULL,
    recipient_last_name character varying(100) NOT NULL,
    paystack_recipient_code character varying(100),
    CONSTRAINT ambassador_payout_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.announcement (\n    id integer DEFAULT nextval('announcement_id_seq'::regclass) NOT NULL,
    title character varying(200) NOT NULL,
    body character varying(500) NOT NULL,
    sent_by integer NOT NULL,
    reach integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT announcement_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.audit_log (\n    id integer DEFAULT nextval('audit_log_id_seq'::regclass) NOT NULL,
    actor_id integer,
    action character varying(60) NOT NULL,
    target_type character varying(40),
    target_id integer,
    details text,
    created_at timestamp without time zone,
    CONSTRAINT audit_log_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.auth_otp (\n    id bigint DEFAULT nextval('auth_otp_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    purpose character varying(30) NOT NULL,
    target character varying(320) NOT NULL,
    code_hash character varying(64) NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    request_ip character varying(64),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    consumed_at timestamp without time zone,
    CONSTRAINT auth_otp_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.b2b_audit_log (\n    id bigint DEFAULT nextval('b2b_audit_log_id_seq'::regclass) NOT NULL,
    organisation_id integer,
    campaign_id bigint,
    actor_user_id integer,
    action character varying(60) NOT NULL,
    from_state character varying(40),
    to_state character varying(40),
    reason text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT b2b_audit_log_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.b2b_campaign_funding (\n    id bigint DEFAULT nextval('b2b_campaign_funding_id_seq'::regclass) NOT NULL,
    campaign_id bigint NOT NULL,
    payment_id bigint NOT NULL,
    amount_minor bigint NOT NULL,
    currency character varying(3) DEFAULT 'KES'::character varying NOT NULL,
    status character varying(30) DEFAULT 'credited'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    reversed_at timestamp without time zone,
    reversal_reason text,
    CONSTRAINT b2b_campaign_funding_payment_id_key UNIQUE (payment_id),
    CONSTRAINT b2b_campaign_funding_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.b2b_campaign_ledger (\n    id bigint DEFAULT nextval('b2b_campaign_ledger_id_seq'::regclass) NOT NULL,
    campaign_id bigint NOT NULL,
    entry_type character varying(40) NOT NULL,
    signed_amount_minor bigint NOT NULL,
    currency character varying(3) DEFAULT 'KES'::character varying NOT NULL,
    idempotency_key character varying(220) NOT NULL,
    payment_id bigint,
    funding_id bigint,
    delivery_event_id bigint,
    reversal_of_entry_id bigint,
    actor_user_id integer,
    description text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT b2b_campaign_ledger_idempotency_key_key UNIQUE (idempotency_key),
    CONSTRAINT b2b_campaign_ledger_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.b2b_invoice (\n    id bigint DEFAULT nextval('b2b_invoice_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    campaign_id bigint,
    invoice_number character varying(80) NOT NULL,
    currency character varying(3) DEFAULT 'KES'::character varying NOT NULL,
    subtotal_minor bigint NOT NULL,
    processing_fee_minor bigint DEFAULT 0 NOT NULL,
    total_minor bigint NOT NULL,
    status character varying(30) DEFAULT 'pro_forma'::character varying NOT NULL,
    payment_method character varying(30) DEFAULT 'bank_transfer'::character varying NOT NULL,
    due_at timestamp without time zone,
    paid_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    etims_status character varying(30) DEFAULT 'not_issued'::character varying NOT NULL,
    etims_invoice_number character varying(120),
    etims_control_code character varying(120),
    etims_issued_at timestamp without time zone,
    CONSTRAINT b2b_invoice_invoice_number_key UNIQUE (invoice_number),
    CONSTRAINT b2b_invoice_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.b2b_payment (\n    id bigint DEFAULT nextval('b2b_payment_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    campaign_id bigint,
    provider character varying(30) DEFAULT 'paystack'::character varying NOT NULL,
    provider_reference character varying(160) NOT NULL,
    currency character varying(3) DEFAULT 'KES'::character varying NOT NULL,
    customer_amount_minor bigint NOT NULL,
    campaign_amount_minor bigint DEFAULT 0 NOT NULL,
    processing_fee_minor bigint DEFAULT 0 NOT NULL,
    status character varying(30) DEFAULT 'pending'::character varying NOT NULL,
    purpose character varying(40) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    paid_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    refund_status character varying(30),
    refunded_amount_minor bigint DEFAULT 0 NOT NULL,
    refund_reference character varying(120),
    refund_requested_at timestamp without time zone,
    refund_processed_at timestamp without time zone,
    CONSTRAINT b2b_payment_pkey PRIMARY KEY (id),
    CONSTRAINT b2b_payment_provider_reference_key UNIQUE (provider_reference)\n);

CREATE TABLE public.b2b_placement_config (\n    id bigint DEFAULT nextval('b2b_placement_config_id_seq'::regclass) NOT NULL,
    placement_key character varying(80) NOT NULL,
    label character varying(160) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    allowed_billing_modes jsonb DEFAULT '["cpm", "cpc"]'::jsonb NOT NULL,
    cpm_amount_minor bigint,
    cpc_amount_minor bigint,
    inventory_limit integer,
    frequency_cap_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    version character varying(80) DEFAULT 'launch-v1'::character varying NOT NULL,
    updated_by_user_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT b2b_placement_config_pkey PRIMARY KEY (id),
    CONSTRAINT b2b_placement_config_placement_key_key UNIQUE (placement_key)\n);

CREATE TABLE public.b2b_pricing_config (\n    id bigint DEFAULT nextval('b2b_pricing_config_id_seq'::regclass) NOT NULL,
    config_key character varying(80) NOT NULL,
    value_json jsonb NOT NULL,
    currency character varying(3) DEFAULT 'KES'::character varying NOT NULL,
    version character varying(80) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    updated_by_user_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT b2b_pricing_config_config_key_key UNIQUE (config_key),
    CONSTRAINT b2b_pricing_config_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.chat_message_idempotency (\n    conversation_id integer NOT NULL,
    sender_id integer NOT NULL,
    client_message_id character varying(128) NOT NULL,
    message_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chat_message_idempotency_pkey PRIMARY KEY (conversation_id, sender_id, client_message_id)\n);

CREATE TABLE public.chat_message_meta (\n    message_id integer NOT NULL,
    conversation_id integer NOT NULL,
    kind character varying(20) DEFAULT 'text'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chat_message_meta_pkey PRIMARY KEY (message_id)\n);

CREATE TABLE public.chat_message_receipt (\n    message_id integer NOT NULL,
    user_id integer NOT NULL,
    delivered_at timestamp without time zone,
    read_at timestamp without time zone,
    CONSTRAINT chat_message_receipt_pkey PRIMARY KEY (message_id, user_id)\n);

CREATE TABLE public.concept_prerequisite (\n    id integer DEFAULT nextval('concept_prerequisite_id_seq'::regclass) NOT NULL,
    concept_id integer NOT NULL,
    prerequisite_concept_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT concept_prerequisite_pkey PRIMARY KEY (id),
    CONSTRAINT uq_concept_prerequisite_pair UNIQUE (concept_id, prerequisite_concept_id)\n);

CREATE TABLE public.content_item (\n    id integer DEFAULT nextval('content_item_id_seq'::regclass) NOT NULL,
    content_type character varying(20) NOT NULL,
    title character varying(200) NOT NULL,
    file_url character varying(500),
    paper_year integer,
    is_downloadable boolean,
    price integer,
    CONSTRAINT content_item_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.content_report (\n    id integer DEFAULT nextval('content_report_id_seq'::regclass) NOT NULL,
    target_type character varying(30) NOT NULL,
    target_id integer NOT NULL,
    reporter_user_id integer,
    reason character varying(40) NOT NULL,
    details character varying(500),
    priority character varying(10) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    action_taken character varying(20),
    admin_notes character varying(500),
    reviewed_by integer,
    reviewed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT content_report_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.conversation (\n    id integer DEFAULT nextval('conversation_id_seq'::regclass) NOT NULL,
    is_group boolean NOT NULL,
    name character varying(100),
    created_by integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    status character varying(20) DEFAULT 'accepted'::character varying NOT NULL,
    e2ee_mode character varying(20) DEFAULT 'legacy'::character varying NOT NULL,
    key_epoch integer DEFAULT 0 NOT NULL,
    CONSTRAINT conversation_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.conversation_key_envelope (\n    id integer DEFAULT nextval('conversation_key_envelope_id_seq'::regclass) NOT NULL,
    conversation_id integer NOT NULL,
    recipient_user_id integer NOT NULL,
    sender_user_id integer NOT NULL,
    key_epoch integer DEFAULT 0 NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    nonce character varying(64) NOT NULL,
    ciphertext text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_conversation_key_envelope_epoch_nonnegative CHECK ((key_epoch >= 0)),
    CONSTRAINT ck_conversation_key_envelope_version_positive CHECK ((version > 0)),
    CONSTRAINT conversation_key_envelope_pkey PRIMARY KEY (id),
    CONSTRAINT uq_conversation_key_envelope_recipient_epoch UNIQUE (conversation_id, recipient_user_id, key_epoch)\n);

CREATE TABLE public.conversation_participant (\n    id integer DEFAULT nextval('conversation_participant_id_seq'::regclass) NOT NULL,
    conversation_id integer NOT NULL,
    user_id integer NOT NULL,
    role character varying(20) NOT NULL,
    joined_at timestamp without time zone,
    last_read_at timestamp without time zone,
    left_at timestamp without time zone,
    muted boolean DEFAULT false NOT NULL,
    CONSTRAINT conversation_participant_pkey PRIMARY KEY (id),
    CONSTRAINT uq_participant_conversation_user UNIQUE (conversation_id, user_id)\n);

CREATE TABLE public.discovery_campaign (\n    id bigint DEFAULT nextval('discovery_campaign_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    opportunity_id integer,
    name character varying(200) NOT NULL,
    objective character varying(30) DEFAULT 'reach'::character varying NOT NULL,
    placement character varying(30) DEFAULT 'feed'::character varying NOT NULL,
    status character varying(30) DEFAULT 'draft'::character varying NOT NULL,
    budget_kes integer DEFAULT 0 NOT NULL,
    bid_type character varying(20) DEFAULT 'cpm'::character varying NOT NULL,
    bid_kes integer DEFAULT 0 NOT NULL,
    target_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    delivered_impressions integer DEFAULT 0 NOT NULL,
    delivered_clicks integer DEFAULT 0 NOT NULL,
    delivered_applications integer DEFAULT 0 NOT NULL,
    push_delivered integer DEFAULT 0 NOT NULL,
    starts_at timestamp without time zone,
    ends_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    currency character varying(3) DEFAULT 'KES'::character varying NOT NULL,
    funding_status character varying(30) DEFAULT 'unfunded'::character varying NOT NULL,
    funded_amount_minor bigint DEFAULT 0 NOT NULL,
    pricing_version character varying(80),
    pricing_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    approved_at timestamp without time zone,
    activated_at timestamp without time zone,
    exhausted_at timestamp without time zone,
    refund_previous_status character varying(30),
    CONSTRAINT discovery_campaign_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.discovery_event (\n    id bigint DEFAULT nextval('discovery_event_id_seq'::regclass) NOT NULL,
    campaign_id bigint NOT NULL,
    user_id integer NOT NULL,
    event_key character varying(180) NOT NULL,
    event_type character varying(30) NOT NULL,
    placement character varying(30) NOT NULL,
    amount_kes numeric(12,4) DEFAULT 0 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT discovery_event_event_key_key UNIQUE (event_key),
    CONSTRAINT discovery_event_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.discovery_push_delivery (\n    id bigint DEFAULT nextval('discovery_push_delivery_id_seq'::regclass) NOT NULL,
    campaign_id bigint NOT NULL,
    user_id integer NOT NULL,
    subscription_endpoint text,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    provider_response text,
    sent_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT discovery_push_delivery_campaign_id_user_id_key UNIQUE (campaign_id, user_id),
    CONSTRAINT discovery_push_delivery_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.document (\n    id integer DEFAULT nextval('document_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    document_content_id integer,
    title character varying(200) NOT NULL,
    original_filename character varying(255) NOT NULL,
    status character varying(20) NOT NULL,
    is_removed boolean NOT NULL,
    reported_at timestamp without time zone,
    report_reason character varying(50),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    last_opened_at timestamp without time zone,
    CONSTRAINT document_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.document_content (\n    id integer DEFAULT nextval('document_content_id_seq'::regclass) NOT NULL,
    content_hash character varying(64) NOT NULL,
    storage_path character varying(500) NOT NULL,
    file_type character varying(20) NOT NULL,
    file_size_bytes integer NOT NULL,
    page_count integer,
    status character varying(20) NOT NULL,
    error_message character varying(500),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    extracted_text text,
    CONSTRAINT document_content_content_hash_key UNIQUE (content_hash),
    CONSTRAINT document_content_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.document_reading_progress (\n    id integer GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    user_id integer NOT NULL,
    document_id integer NOT NULL,
    page_num integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_document_reading_progress_page_nonnegative CHECK ((page_num >= 0)),
    CONSTRAINT document_reading_progress_pkey PRIMARY KEY (id),
    CONSTRAINT uq_document_reading_progress_user_document UNIQUE (user_id, document_id)\n);

CREATE TABLE public.flashcard_session (\n    id integer DEFAULT nextval('flashcard_session_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    generated_material_id integer NOT NULL,
    document_content_id integer NOT NULL,
    cards_reviewed integer,
    created_at timestamp without time zone,
    CONSTRAINT flashcard_session_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.follow (\n    id integer DEFAULT nextval('follow_id_seq'::regclass) NOT NULL,
    follower_id integer NOT NULL,
    followed_id integer NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT follow_pkey PRIMARY KEY (id),
    CONSTRAINT uq_follow_follower_followed UNIQUE (follower_id, followed_id)\n);

CREATE TABLE public.follow_request (\n    id integer DEFAULT nextval('follow_request_id_seq'::regclass) NOT NULL,
    requester_id integer NOT NULL,
    target_id integer NOT NULL,
    status character varying(10) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    responded_at timestamp without time zone,
    CONSTRAINT follow_request_pkey PRIMARY KEY (id),
    CONSTRAINT uq_follow_request_requester_target UNIQUE (requester_id, target_id)\n);

CREATE TABLE public.forum_post (\n    id integer DEFAULT nextval('forum_post_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    title character varying(200) NOT NULL,
    body text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    is_removed boolean DEFAULT false NOT NULL,
    CONSTRAINT forum_post_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.forum_reply (\n    id integer DEFAULT nextval('forum_reply_id_seq'::regclass) NOT NULL,
    post_id integer NOT NULL,
    user_id integer,
    is_ai boolean DEFAULT false NOT NULL,
    ai_answer_id integer,
    triggered_by_user_id integer,
    body text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    is_removed boolean DEFAULT false NOT NULL,
    CONSTRAINT forum_reply_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.generated_material (\n    id integer DEFAULT nextval('generated_material_id_seq'::regclass) NOT NULL,
    document_content_id integer NOT NULL,
    material_type character varying(20) NOT NULL,
    status character varying(20) NOT NULL,
    payload text,
    error_message character varying(500),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    is_flagged boolean DEFAULT false NOT NULL,
    flagged_reason character varying(500),
    flagged_by integer,
    flagged_at timestamp without time zone,
    generation_fingerprint character varying(128) NOT NULL,
    generation_parameters jsonb,
    generation_version character varying(50) DEFAULT 'v1'::character varying NOT NULL,
    scope character varying(20) DEFAULT 'shared'::character varying NOT NULL,
    owner_user_id integer,
    CONSTRAINT generated_material_pkey PRIMARY KEY (id)\n);

CREATE TABLE public."group" (\n    id integer DEFAULT nextval('group_id_seq'::regclass) NOT NULL,
    name character varying(150) NOT NULL,
    description character varying(1000),
    privacy character varying(20) NOT NULL,
    university_id integer,
    program_id integer,
    year integer,
    created_by integer NOT NULL,
    member_count integer NOT NULL,
    created_at timestamp without time zone,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT group_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.group_file (\n    id integer DEFAULT nextval('group_file_id_seq'::regclass) NOT NULL,
    group_id integer NOT NULL,
    document_id integer NOT NULL,
    shared_by_user_id integer NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT group_file_pkey PRIMARY KEY (id),
    CONSTRAINT uq_group_file_group_document UNIQUE (group_id, document_id)\n);

CREATE TABLE public.group_member (\n    id integer DEFAULT nextval('group_member_id_seq'::regclass) NOT NULL,
    group_id integer NOT NULL,
    user_id integer NOT NULL,
    role character varying(20) NOT NULL,
    joined_at timestamp without time zone,
    CONSTRAINT group_member_pkey PRIMARY KEY (id),
    CONSTRAINT uq_group_member_group_user UNIQUE (group_id, user_id)\n);

CREATE TABLE public.group_post (\n    id integer DEFAULT nextval('group_post_id_seq'::regclass) NOT NULL,
    group_id integer NOT NULL,
    user_id integer NOT NULL,
    post_type character varying(20) NOT NULL,
    body text NOT NULL,
    created_at timestamp without time zone,
    is_removed boolean DEFAULT false NOT NULL,
    CONSTRAINT group_post_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.group_post_comment (\n    id integer DEFAULT nextval('group_post_comment_id_seq'::regclass) NOT NULL,
    group_post_id integer NOT NULL,
    user_id integer NOT NULL,
    body text NOT NULL,
    created_at timestamp without time zone,
    marked_helpful boolean DEFAULT false NOT NULL,
    is_removed boolean DEFAULT false NOT NULL,
    CONSTRAINT group_post_comment_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.group_post_like (\n    id integer DEFAULT nextval('group_post_like_id_seq'::regclass) NOT NULL,
    group_post_id integer NOT NULL,
    user_id integer NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT group_post_like_pkey PRIMARY KEY (id),
    CONSTRAINT uq_group_post_like_post_user UNIQUE (group_post_id, user_id)\n);

CREATE TABLE public.group_question_vote (\n    id integer DEFAULT nextval('group_question_vote_id_seq'::regclass) NOT NULL,
    group_post_id integer NOT NULL,
    user_id integer NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT group_question_vote_pkey PRIMARY KEY (id),
    CONSTRAINT uq_group_question_vote_post_user UNIQUE (group_post_id, user_id)\n);

CREATE TABLE public.kokoro_gpu_scaling_decisions (\n    id bigint DEFAULT nextval('kokoro_gpu_scaling_decisions_id_seq'::regclass) NOT NULL,
    action character varying(32) NOT NULL,
    reason_code character varying(80) NOT NULL,
    reason_text character varying(1000) NOT NULL,
    dry_run boolean DEFAULT true NOT NULL,
    pending_jobs integer DEFAULT 0 NOT NULL,
    processing_jobs integer DEFAULT 0 NOT NULL,
    queue_depth integer DEFAULT 0 NOT NULL,
    oldest_pending_age_seconds integer,
    queued_audio_seconds numeric(14,2) DEFAULT 0 NOT NULL,
    current_workers integer DEFAULT 0 NOT NULL,
    desired_workers integer DEFAULT 0 NOT NULL,
    target_workers integer DEFAULT 0 NOT NULL,
    max_workers integer DEFAULT 1 NOT NULL,
    max_pending_jobs_per_worker integer DEFAULT 3 NOT NULL,
    max_pending_age_seconds integer DEFAULT 120 NOT NULL,
    max_gpu_price_usd_per_hour numeric(12,6),
    max_gpu_hourly_spend_usd numeric(12,6),
    estimated_incremental_hourly_usd numeric(12,6),
    gpu_name character varying(120),
    gpu_vram_gb numeric(8,2),
    vram_used_gb numeric(8,2),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    provider_credit_usd numeric(12,6),
    provider_credit_reserve_usd numeric(12,6),
    host_ram_gb numeric(8,2),
    required_vram_gb numeric(8,2),
    required_host_ram_gb numeric(8,2),
    projected_hourly_spend_usd numeric(12,6),
    decision_context jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT kokoro_gpu_scaling_decisions_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.kokoro_gpu_workers (\n    id bigint DEFAULT nextval('kokoro_gpu_workers_id_seq'::regclass) NOT NULL,
    provider character varying(32) DEFAULT 'vast'::character varying NOT NULL,
    instance_id bigint NOT NULL,
    offer_id bigint,
    gpu_name character varying(120) NOT NULL,
    gpu_vram_gb numeric(8,2),
    status character varying(32) DEFAULT 'starting'::character varying NOT NULL,
    worker_index integer DEFAULT 1 NOT NULL,
    worker_capacity integer DEFAULT 1 NOT NULL,
    price_usd_per_hour numeric(12,6),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_job_at timestamp without time zone,
    last_idle_at timestamp without time zone,
    last_heartbeat_at timestamp without time zone,
    vram_used_gb numeric(8,2),
    vram_total_gb numeric(8,2),
    last_error character varying(1000),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    worker_id character varying(64),
    host_ram_gb numeric(8,2),
    required_vram_gb numeric(8,2),
    required_host_ram_gb numeric(8,2),
    CONSTRAINT kokoro_gpu_workers_instance_id_key UNIQUE (instance_id),
    CONSTRAINT kokoro_gpu_workers_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.learning_concept (\n    id integer DEFAULT nextval('learning_concept_id_seq'::regclass) NOT NULL,
    name character varying(200) NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT learning_concept_name_key UNIQUE (name),
    CONSTRAINT learning_concept_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.learning_event (\n    id integer DEFAULT nextval('learning_event_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    concept_id integer NOT NULL,
    tutor_message_id integer,
    document_content_id integer,
    evidence_snippet character varying(500),
    misconception character varying(300),
    created_at timestamp without time zone,
    CONSTRAINT learning_event_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.library_publication (\n    id integer DEFAULT nextval('library_publication_id_seq'::regclass) NOT NULL,
    document_id integer NOT NULL,
    user_id integer NOT NULL,
    title character varying(200) NOT NULL,
    description character varying(1000),
    material_type character varying(30) NOT NULL,
    status character varying(20) NOT NULL,
    rejection_reason character varying(500),
    reviewed_by integer,
    reviewed_at timestamp without time zone,
    view_count integer NOT NULL,
    save_count integer NOT NULL,
    xp_awarded boolean NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    university_id integer,
    program_id integer,
    year integer,
    semester integer,
    CONSTRAINT library_publication_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.library_report (\n    id integer DEFAULT nextval('library_report_id_seq'::regclass) NOT NULL,
    library_publication_id integer NOT NULL,
    reporter_user_id integer NOT NULL,
    reason character varying(50) NOT NULL,
    details character varying(500),
    status character varying(20) NOT NULL,
    reviewed_by integer,
    reviewed_at timestamp without time zone,
    admin_notes character varying(500),
    created_at timestamp without time zone,
    CONSTRAINT library_report_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.message (\n    id integer DEFAULT nextval('message_id_seq'::regclass) NOT NULL,
    conversation_id integer NOT NULL,
    sender_id integer NOT NULL,
    body text,
    is_deleted boolean NOT NULL,
    created_at timestamp without time zone,
    edited_at timestamp without time zone,
    nonce character varying(64),
    e2ee_key_epoch integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_message_e2ee_key_epoch_nonnegative CHECK ((e2ee_key_epoch >= 0)),
    CONSTRAINT message_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.message_attachment (\n    id integer DEFAULT nextval('message_attachment_id_seq'::regclass) NOT NULL,
    conversation_id integer NOT NULL,
    message_id integer,
    uploaded_by_user_id integer NOT NULL,
    storage_path character varying(500) NOT NULL,
    file_type character varying(20) NOT NULL,
    original_filename character varying(255) NOT NULL,
    file_size_bytes integer NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp without time zone,
    cached_view_url character varying(1000),
    cached_view_url_expires_at timestamp without time zone,
    CONSTRAINT message_attachment_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.notification (\n    id integer DEFAULT nextval('notification_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    type character varying(40) NOT NULL,
    title character varying(200) NOT NULL,
    body character varying(500),
    related_type character varying(40),
    related_id integer,
    is_read boolean NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT notification_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.notification_preference (\n    id integer DEFAULT nextval('notification_preference_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    community_enabled boolean DEFAULT true NOT NULL,
    messages_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    CONSTRAINT notification_preference_pkey PRIMARY KEY (id),
    CONSTRAINT notification_preference_user_id_key UNIQUE (user_id)\n);

CREATE TABLE public.opportunity (\n    id integer DEFAULT nextval('opportunity_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    created_by integer NOT NULL,
    title character varying(200) NOT NULL,
    description text NOT NULL,
    opportunity_type character varying(20) NOT NULL,
    location character varying(200),
    is_remote boolean NOT NULL,
    application_url character varying(500),
    application_instructions text,
    application_deadline timestamp without time zone NOT NULL,
    expiry_date timestamp without time zone NOT NULL,
    status character varying(20) NOT NULL,
    rejection_reason character varying(500),
    submitted_at timestamp without time zone,
    reviewed_by integer,
    reviewed_at timestamp without time zone,
    published_at timestamp without time zone,
    view_count integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    organic_free_impression_cap integer DEFAULT 5000 NOT NULL,
    organic_free_cap_reached_at timestamp without time zone,
    CONSTRAINT opportunity_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.opportunity_promotion (\n    id integer DEFAULT nextval('opportunity_promotion_id_seq'::regclass) NOT NULL,
    opportunity_id integer NOT NULL,
    organisation_id integer NOT NULL,
    promotion_type character varying(20) NOT NULL,
    start_date timestamp without time zone NOT NULL,
    end_date timestamp without time zone NOT NULL,
    price integer NOT NULL,
    payment_status character varying(20) NOT NULL,
    approval_status character varying(20) NOT NULL,
    reviewed_by integer,
    reviewed_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    CONSTRAINT opportunity_promotion_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.opportunity_view_event (\n    id bigint DEFAULT nextval('opportunity_view_event_id_seq'::regclass) NOT NULL,
    opportunity_id integer NOT NULL,
    user_id integer NOT NULL,
    source character varying(20) DEFAULT 'organic'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT opportunity_view_event_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.organisation (\n    id integer DEFAULT nextval('organisation_id_seq'::regclass) NOT NULL,
    name character varying(150) NOT NULL,
    description character varying(1000),
    website character varying(500),
    logo_url character varying(500),
    contact_email character varying(120) NOT NULL,
    contact_phone character varying(20),
    verification_status character varying(20) NOT NULL,
    verification_notes character varying(500),
    is_active boolean NOT NULL,
    created_by integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    CONSTRAINT organisation_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.organisation_billing (\n    organisation_id integer NOT NULL,
    plan_code character varying(30) DEFAULT 'launch'::character varying NOT NULL,
    status character varying(20) DEFAULT 'trial'::character varying NOT NULL,
    monthly_fee_kes integer,
    active_user_cap integer,
    started_at timestamp without time zone,
    expires_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    transaction_reference character varying(120),
    checkout_url text,
    CONSTRAINT organisation_billing_pkey PRIMARY KEY (organisation_id)\n);

CREATE TABLE public.organisation_billing_event (\n    id bigint DEFAULT nextval('organisation_billing_event_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    event_key character varying(120) NOT NULL,
    event_type character varying(40) NOT NULL,
    amount_kes integer DEFAULT 0 NOT NULL,
    status character varying(30) DEFAULT 'recorded'::character varying NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT organisation_billing_event_event_key_key UNIQUE (event_key),
    CONSTRAINT organisation_billing_event_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.organisation_campaign_meter (\n    organisation_id integer NOT NULL,
    period_start date NOT NULL,
    impressions integer DEFAULT 0 NOT NULL,
    clicks integer DEFAULT 0 NOT NULL,
    applications integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT organisation_campaign_meter_pkey PRIMARY KEY (organisation_id, period_start)\n);

CREATE TABLE public.organisation_invoice (\n    id bigint DEFAULT nextval('organisation_invoice_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    plan_code character varying(30) NOT NULL,
    amount_kes integer NOT NULL,
    status character varying(30) DEFAULT 'pending'::character varying NOT NULL,
    payment_reference character varying(120),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    paid_at timestamp without time zone,
    CONSTRAINT organisation_invoice_organisation_id_period_start_period_en_key UNIQUE (organisation_id, period_start, period_end),
    CONSTRAINT organisation_invoice_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.organisation_kyc_document (\n    id bigint DEFAULT nextval('organisation_kyc_document_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    document_type character varying(60) NOT NULL,
    file_name character varying(255),
    storage_path text,
    status character varying(30) DEFAULT 'pending'::character varying NOT NULL,
    admin_notes text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    reviewed_at timestamp without time zone,
    reviewed_by integer,
    size_bytes bigint,
    sha256 character varying(64),
    mime_type character varying(120),
    storage_provider character varying(20) DEFAULT 'supabase'::character varying NOT NULL,
    CONSTRAINT organisation_kyc_document_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.organisation_member (\n    id integer DEFAULT nextval('organisation_member_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    user_id integer NOT NULL,
    role character varying(20) NOT NULL,
    joined_at timestamp without time zone,
    CONSTRAINT organisation_member_pkey PRIMARY KEY (id),
    CONSTRAINT uq_org_member_org_user UNIQUE (organisation_id, user_id)\n);

CREATE TABLE public.organisation_plan_config (\n    plan_code character varying(20) NOT NULL,
    monthly_fee_kes integer NOT NULL,
    active_user_cap integer NOT NULL,
    active_opportunities integer DEFAULT 0 NOT NULL,
    sponsored_campaigns integer DEFAULT 0 NOT NULL,
    candidate_search_window_days integer DEFAULT 7 NOT NULL,
    analytics_retention_days integer DEFAULT 30 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT organisation_plan_config_pkey PRIMARY KEY (plan_code)\n);

CREATE TABLE public.organisation_usage_invoice (\n    id bigint DEFAULT nextval('organisation_usage_invoice_id_seq'::regclass) NOT NULL,
    organisation_id integer NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    usage_type character varying(40) DEFAULT 'discovery'::character varying NOT NULL,
    amount_kes integer DEFAULT 0 NOT NULL,
    status character varying(30) DEFAULT 'pending'::character varying NOT NULL,
    payment_reference character varying(120),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    paid_at timestamp without time zone,
    CONSTRAINT organisation_usage_invoice_organisation_id_period_start_per_key UNIQUE (organisation_id, period_start, period_end, usage_type),
    CONSTRAINT organisation_usage_invoice_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.payment (\n    id integer DEFAULT nextval('payment_id_seq'::regclass) NOT NULL,
    phone_number character varying(20),
    amount integer NOT NULL,
    checkout_request_id character varying(100),
    status character varying(20),
    created_at timestamp without time zone,
    user_id integer,
    content_item_id integer,
    provider character varying(20) DEFAULT 'paystack'::character varying NOT NULL,
    reference character varying(50),
    provider_reference character varying(100),
    payment_type character varying(20) DEFAULT 'content'::character varying NOT NULL,
    plan character varying(20),
    subscription_expires_at timestamp without time zone,
    subscription_starts_at timestamp without time zone,
    subscription_allowance_snapshot jsonb,
    CONSTRAINT payment_checkout_request_id_key UNIQUE (checkout_request_id),
    CONSTRAINT payment_merchant_reference_key UNIQUE (reference),
    CONSTRAINT payment_order_tracking_id_key UNIQUE (provider_reference),
    CONSTRAINT payment_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.product_activity_day (\n    user_id integer NOT NULL,
    activity_date date NOT NULL,
    sessions integer DEFAULT 0 NOT NULL,
    engaged_seconds integer DEFAULT 0 NOT NULL,
    core_actions integer DEFAULT 0 NOT NULL,
    last_seen_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT product_activity_day_pkey PRIMARY KEY (user_id, activity_date)\n);

CREATE TABLE public.program (\n    id integer DEFAULT nextval('program_id_seq'::regclass) NOT NULL,
    university_id integer NOT NULL,
    name character varying(150) NOT NULL,
    degree_level character varying(50),
    discipline_category character varying(80),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT program_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.push_subscription (\n    id integer DEFAULT nextval('push_subscription_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    endpoint character varying(500) NOT NULL,
    p256dh_key character varying(255) NOT NULL,
    auth_key character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT push_subscription_endpoint_key UNIQUE (endpoint),
    CONSTRAINT push_subscription_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.quiz_attempt (\n    id integer DEFAULT nextval('quiz_attempt_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    generated_material_id integer NOT NULL,
    document_content_id integer NOT NULL,
    score_percent integer,
    created_at timestamp without time zone,
    CONSTRAINT quiz_attempt_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.referral (\n    id integer DEFAULT nextval('referral_id_seq'::regclass) NOT NULL,
    ambassador_id integer NOT NULL,
    referred_user_id integer NOT NULL,
    referral_code_used character varying(20) NOT NULL,
    channel character varying(30),
    status character varying(20) NOT NULL,
    verified_at timestamp without time zone,
    activated_at timestamp without time zone,
    first_payment_id integer,
    first_payment_at timestamp without time zone,
    commission_rate_applied integer,
    commission_amount integer,
    unlock_at timestamp without time zone,
    payout_id integer,
    voided_at timestamp without time zone,
    void_reason character varying(200),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    CONSTRAINT referral_first_payment_id_key UNIQUE (first_payment_id),
    CONSTRAINT referral_pkey PRIMARY KEY (id),
    CONSTRAINT referral_referred_user_id_key UNIQUE (referred_user_id)\n);

CREATE TABLE public.saved_library_material (\n    id integer DEFAULT nextval('saved_library_material_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    library_publication_id integer NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT saved_library_material_pkey PRIMARY KEY (id),
    CONSTRAINT uq_saved_material_user_pub UNIQUE (user_id, library_publication_id)\n);

CREATE TABLE public.saved_opportunity (\n    id integer DEFAULT nextval('saved_opportunity_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    opportunity_id integer NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT saved_opportunity_pkey PRIMARY KEY (id),
    CONSTRAINT uq_saved_opportunity_user_opp UNIQUE (user_id, opportunity_id)\n);

CREATE TABLE public.student_ai_usage (\n    user_id integer NOT NULL,
    period_start date NOT NULL,
    feature character varying(40) NOT NULL,
    units integer DEFAULT 0 NOT NULL,
    requests integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT student_ai_usage_pkey PRIMARY KEY (user_id, period_start, feature)\n);

CREATE TABLE public.student_concept_mastery (\n    id integer DEFAULT nextval('student_concept_mastery_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    concept_id integer NOT NULL,
    mastery_score integer DEFAULT 0 NOT NULL,
    confidence character varying(20) DEFAULT 'low'::character varying NOT NULL,
    exposure_count integer DEFAULT 0 NOT NULL,
    misconception_count integer DEFAULT 0 NOT NULL,
    last_practiced_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT student_concept_mastery_pkey PRIMARY KEY (id),
    CONSTRAINT uq_concept_mastery_user_concept UNIQUE (user_id, concept_id)\n);

CREATE TABLE public.student_entitlement_usage (\n    id bigint DEFAULT nextval('student_entitlement_usage_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    payment_id integer,
    feature character varying(40) NOT NULL,
    units bigint NOT NULL,
    request_count integer DEFAULT 1 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT student_entitlement_usage_pkey PRIMARY KEY (id),
    CONSTRAINT student_entitlement_usage_request_count_check CHECK ((request_count > 0)),
    CONSTRAINT student_entitlement_usage_units_check CHECK ((units > 0))\n);

CREATE TABLE public.student_learning_profile (\n    id integer DEFAULT nextval('student_learning_profile_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    preferred_explanation_style character varying(30),
    prefers_examples boolean,
    prefers_theory_vs_practice character varying(20),
    preferred_difficulty character varying(20),
    typical_session_length_minutes integer,
    learning_pace character varying(20),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    CONSTRAINT student_learning_profile_pkey PRIMARY KEY (id),
    CONSTRAINT student_learning_profile_user_id_key UNIQUE (user_id)\n);

CREATE TABLE public.student_opportunity_discovery (\n    user_id integer NOT NULL,
    discoverable boolean DEFAULT false NOT NULL,
    consent_version character varying(40) DEFAULT 'g5-v1'::character varying NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT student_opportunity_discovery_pkey PRIMARY KEY (user_id)\n);

CREATE TABLE public.student_opportunity_discovery_audit (\n    id bigint DEFAULT nextval('student_opportunity_discovery_audit_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    discoverable boolean NOT NULL,
    consent_version character varying(40) NOT NULL,
    source character varying(40) DEFAULT 'settings'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT student_opportunity_discovery_audit_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.student_order (\n    id bigint DEFAULT nextval('student_order_id_seq'::regclass) NOT NULL,
    order_number character varying(40) NOT NULL,
    user_id integer NOT NULL,
    payment_id integer NOT NULL,
    order_type character varying(30) NOT NULL,
    item_id integer,
    item_title_snapshot character varying(200) NOT NULL,
    item_file_url_snapshot character varying(500),
    plan character varying(20),
    quantity integer DEFAULT 1 NOT NULL,
    unit_amount integer NOT NULL,
    total_amount integer NOT NULL,
    currency character varying(3) DEFAULT 'KES'::character varying NOT NULL,
    requested_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    fulfillment_payload jsonb,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    paid_at timestamp without time zone,
    fulfilled_at timestamp without time zone,
    refunded_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    checkout_url text,
    CONSTRAINT ck_student_order_currency_kes CHECK (((currency)::text = 'KES'::text)),
    CONSTRAINT ck_student_order_plan_allowed CHECK (((((order_type)::text = 'subscription'::text) AND ((plan)::text = ANY ((ARRAY['plus'::character varying, 'pro'::character varying])::text[]))) OR (((order_type)::text = 'content'::text) AND (plan IS NULL)))),
    CONSTRAINT ck_student_order_quantity_positive CHECK ((quantity = 1)),
    CONSTRAINT ck_student_order_status_allowed CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'paid'::character varying, 'fulfilled'::character varying, 'failed'::character varying, 'refunded'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT ck_student_order_total_matches_unit CHECK ((total_amount = (unit_amount * quantity))),
    CONSTRAINT ck_student_order_type_allowed CHECK (((order_type)::text = ANY ((ARRAY['subscription'::character varying, 'content'::character varying])::text[]))),
    CONSTRAINT ck_student_order_type_snapshot CHECK (((((order_type)::text = 'subscription'::text) AND (item_id IS NULL) AND ((plan)::text = ANY ((ARRAY['plus'::character varying, 'pro'::character varying])::text[]))) OR (((order_type)::text = 'content'::text) AND (item_id IS NOT NULL) AND (plan IS NULL)))),
    CONSTRAINT student_order_order_number_key UNIQUE (order_number),
    CONSTRAINT student_order_payment_id_key UNIQUE (payment_id),
    CONSTRAINT student_order_pkey PRIMARY KEY (id),
    CONSTRAINT student_order_quantity_check CHECK ((quantity > 0)),
    CONSTRAINT student_order_total_amount_check CHECK ((total_amount >= 0)),
    CONSTRAINT student_order_unit_amount_check CHECK ((unit_amount >= 0))\n);

CREATE TABLE public.student_plan_config (\n    plan_code character varying(20) NOT NULL,
    display_name character varying(40) NOT NULL,
    price_kes integer DEFAULT 0 NOT NULL,
    billing_period character varying(20) DEFAULT 'month'::character varying NOT NULL,
    quota_period character varying(20) DEFAULT 'month'::character varying NOT NULL,
    ada_monthly_units bigint DEFAULT 0 NOT NULL,
    ada_daily_units bigint DEFAULT 0 NOT NULL,
    ada_max_output_tokens integer DEFAULT 800 NOT NULL,
    podcast_minutes integer DEFAULT 0 NOT NULL,
    summary_pages integer DEFAULT 0 NOT NULL,
    questions integer DEFAULT 0 NOT NULL,
    mind_map_nodes integer DEFAULT 0 NOT NULL,
    flashcards integer DEFAULT 0 NOT NULL,
    offline_study boolean DEFAULT true NOT NULL,
    premium_library boolean DEFAULT false NOT NULL,
    study_hub_uploads boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by integer,
    CONSTRAINT student_plan_config_pkey PRIMARY KEY (plan_code)\n);

CREATE TABLE public.student_refund_request (\n    id bigint DEFAULT nextval('student_refund_request_id_seq'::regclass) NOT NULL,
    payment_id integer NOT NULL,
    user_id integer NOT NULL,
    requested_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status character varying(30) DEFAULT 'requested'::character varying NOT NULL,
    requested_amount integer,
    approved_amount integer,
    consumed_value_kes integer DEFAULT 0 NOT NULL,
    retention_amount_kes integer DEFAULT 0 NOT NULL,
    reason character varying(500),
    admin_user_id integer,
    admin_reason character varying(500),
    paystack_refund_id character varying(100),
    paystack_status character varying(30),
    processed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    paystack_transaction_reference character varying(120),
    paystack_refund_reference character varying(120),
    provider_message character varying(500),
    CONSTRAINT student_refund_request_payment_id_key UNIQUE (payment_id),
    CONSTRAINT student_refund_request_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.student_subscription (\n    id bigint DEFAULT nextval('student_subscription_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    plan character varying(20) NOT NULL,
    paystack_plan_code character varying(80) NOT NULL,
    paystack_subscription_code character varying(100),
    paystack_email_token character varying(200),
    paystack_customer_code character varying(100),
    status character varying(30) DEFAULT 'active'::character varying NOT NULL,
    cancel_at_period_end boolean DEFAULT false NOT NULL,
    next_payment_at timestamp without time zone,
    current_period_start timestamp without time zone,
    current_period_end timestamp without time zone,
    initial_payment_id integer,
    latest_payment_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT student_subscription_paystack_subscription_code_key UNIQUE (paystack_subscription_code),
    CONSTRAINT student_subscription_pkey PRIMARY KEY (id),
    CONSTRAINT student_subscription_plan_check CHECK (((plan)::text = ANY ((ARRAY['plus'::character varying, 'pro'::character varying])::text[]))),
    CONSTRAINT student_subscription_user_id_paystack_plan_code_key UNIQUE (user_id, paystack_plan_code)\n);

CREATE TABLE public.study_activity_log (\n    id integer DEFAULT nextval('study_activity_log_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    document_content_id integer,
    activity_date date NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT study_activity_log_pkey PRIMARY KEY (id),
    CONSTRAINT uq_study_activity_user_doc_date UNIQUE (user_id, document_content_id, activity_date)\n);

CREATE TABLE public.study_friend_streak (\n    id character varying(36) NOT NULL,
    user_a_id integer NOT NULL,
    user_b_id integer NOT NULL,
    invited_by integer NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    current_streak integer DEFAULT 0 NOT NULL,
    longest_streak integer DEFAULT 0 NOT NULL,
    last_shared_date date,
    weekend_pause boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT study_friend_streak_pkey PRIMARY KEY (id),
    CONSTRAINT study_friend_streak_user_a_id_user_b_id_key UNIQUE (user_a_id, user_b_id)\n);

CREATE TABLE public.study_friend_streak_activity (\n    id character varying(36) NOT NULL,
    streak_id character varying(36) NOT NULL,
    user_a_id integer NOT NULL,
    user_b_id integer NOT NULL,
    activity_date date NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT study_friend_streak_activity_pkey PRIMARY KEY (id),
    CONSTRAINT study_friend_streak_activity_streak_id_activity_date_key UNIQUE (streak_id, activity_date)\n);

CREATE TABLE public.study_streak (\n    id integer DEFAULT nextval('study_streak_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    current_streak integer DEFAULT 0 NOT NULL,
    longest_streak integer DEFAULT 0 NOT NULL,
    last_study_date date,
    updated_at timestamp without time zone,
    CONSTRAINT study_streak_pkey PRIMARY KEY (id),
    CONSTRAINT study_streak_user_id_key UNIQUE (user_id)\n);

CREATE TABLE public.study_time_log (\n    id integer DEFAULT nextval('study_time_log_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    activity_date date NOT NULL,
    study_time_seconds integer DEFAULT 0 NOT NULL,
    last_heartbeat_at timestamp without time zone,
    feature character varying(20) DEFAULT 'reading'::character varying NOT NULL,
    CONSTRAINT study_time_log_pkey PRIMARY KEY (id),
    CONSTRAINT uq_study_time_user_date_feature UNIQUE (user_id, activity_date, feature)\n);

CREATE TABLE public.system_setting (\n    id integer DEFAULT nextval('system_setting_id_seq'::regclass) NOT NULL,
    key character varying(50) NOT NULL,
    value text DEFAULT ''::text NOT NULL,
    CONSTRAINT system_setting_key_key UNIQUE (key),
    CONSTRAINT system_setting_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.tutor_conversation (\n    id integer DEFAULT nextval('tutor_conversation_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    document_content_id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    CONSTRAINT tutor_conversation_pkey PRIMARY KEY (id),
    CONSTRAINT uq_tutor_conv_user_doc UNIQUE (user_id, document_content_id)\n);

CREATE TABLE public.tutor_message (\n    id integer DEFAULT nextval('tutor_message_id_seq'::regclass) NOT NULL,
    conversation_id integer NOT NULL,
    role character varying(10) NOT NULL,
    content text NOT NULL,
    created_at timestamp without time zone,
    CONSTRAINT tutor_message_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.university (\n    id integer DEFAULT nextval('university_id_seq'::regclass) NOT NULL,
    name character varying(150) NOT NULL,
    short_code character varying(20) NOT NULL,
    country character varying(80),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT university_pkey PRIMARY KEY (id),
    CONSTRAINT university_short_code_key UNIQUE (short_code)\n);

CREATE TABLE public."user" (\n    id integer DEFAULT nextval('user_id_seq'::regclass) NOT NULL,
    email character varying(120) NOT NULL,
    password_hash character varying(255) NOT NULL,
    year integer,
    semester integer,
    email_verified boolean DEFAULT false,
    verification_token character varying(64),
    reset_token character varying(64),
    reset_token_expiry timestamp without time zone,
    display_name character varying(50),
    bio character varying(160),
    is_admin boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    signup_source character varying(100),
    is_suspended boolean DEFAULT false NOT NULL,
    university_id integer,
    program_id integer,
    requested_program_name character varying(150),
    last_active_at timestamp without time zone,
    phone_number character varying(20),
    profile_visibility character varying(10) DEFAULT 'public'::character varying NOT NULL,
    who_can_message character varying(10) DEFAULT 'everyone'::character varying NOT NULL,
    who_can_follow character varying(20) DEFAULT 'everyone'::character varying NOT NULL,
    session_version integer DEFAULT 0 NOT NULL,
    CONSTRAINT user_email_key UNIQUE (email),
    CONSTRAINT user_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.user_achievement (\n    id integer DEFAULT nextval('user_achievement_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    achievement_code character varying(40) NOT NULL,
    unlocked_at timestamp without time zone,
    CONSTRAINT uq_user_achievement_user_code UNIQUE (user_id, achievement_code),
    CONSTRAINT user_achievement_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.user_key (\n    id integer DEFAULT nextval('user_key_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    public_key text NOT NULL,
    encrypted_private_key text,
    kdf_salt character varying(64),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    CONSTRAINT user_key_pkey PRIMARY KEY (id),
    CONSTRAINT user_key_user_id_key UNIQUE (user_id)\n);

CREATE TABLE public.user_warning (\n    id integer DEFAULT nextval('user_warning_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    issued_by integer NOT NULL,
    content_report_id integer,
    reason character varying(40) NOT NULL,
    message character varying(500) NOT NULL,
    consequence character varying(500) NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT user_warning_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.view_progress (\n    id integer DEFAULT nextval('view_progress_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    content_item_id integer NOT NULL,
    page_num integer DEFAULT 0,
    updated_at timestamp without time zone DEFAULT now(),
    CONSTRAINT uq_view_progress_user_item UNIQUE (user_id, content_item_id),
    CONSTRAINT view_progress_pkey PRIMARY KEY (id)\n);

CREATE TABLE public.xp_event (\n    id integer DEFAULT nextval('xp_event_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    event_type character varying(40) NOT NULL,
    xp_amount integer NOT NULL,
    related_id integer,
    created_at timestamp without time zone,
    CONSTRAINT uq_xp_event_user_type_related UNIQUE (user_id, event_type, related_id),
    CONSTRAINT xp_event_pkey PRIMARY KEY (id)\n);

-- Foreign keys
ALTER TABLE public.ai_job ADD CONSTRAINT ai_job_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.ai_job ADD CONSTRAINT ai_job_material_id_fkey FOREIGN KEY (material_id) REFERENCES generated_material(id);
ALTER TABLE public.ai_job ADD CONSTRAINT ai_job_notification_id_fkey FOREIGN KEY (notification_id) REFERENCES notification(id);
ALTER TABLE public.ai_usage_log ADD CONSTRAINT ai_usage_log_forum_reply_id_fkey FOREIGN KEY (forum_reply_id) REFERENCES forum_reply(id);
ALTER TABLE public.ai_usage_log ADD CONSTRAINT ai_usage_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.ambassador ADD CONSTRAINT ambassador_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id);
ALTER TABLE public.ambassador ADD CONSTRAINT ambassador_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.ambassador_payout ADD CONSTRAINT ambassador_payout_ambassador_id_fkey FOREIGN KEY (ambassador_id) REFERENCES ambassador(id);
ALTER TABLE public.ambassador_payout ADD CONSTRAINT ambassador_payout_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id);
ALTER TABLE public.announcement ADD CONSTRAINT announcement_sent_by_fkey FOREIGN KEY (sent_by) REFERENCES "user"(id);
ALTER TABLE public.audit_log ADD CONSTRAINT audit_log_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES "user"(id);
ALTER TABLE public.auth_otp ADD CONSTRAINT auth_otp_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE;
ALTER TABLE public.concept_prerequisite ADD CONSTRAINT concept_prerequisite_concept_id_fkey FOREIGN KEY (concept_id) REFERENCES learning_concept(id);
ALTER TABLE public.concept_prerequisite ADD CONSTRAINT concept_prerequisite_prerequisite_concept_id_fkey FOREIGN KEY (prerequisite_concept_id) REFERENCES learning_concept(id);
ALTER TABLE public.content_report ADD CONSTRAINT content_report_reporter_user_id_fkey FOREIGN KEY (reporter_user_id) REFERENCES "user"(id);
ALTER TABLE public.content_report ADD CONSTRAINT content_report_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id);
ALTER TABLE public.conversation ADD CONSTRAINT conversation_created_by_fkey FOREIGN KEY (created_by) REFERENCES "user"(id);
ALTER TABLE public.conversation_key_envelope ADD CONSTRAINT conversation_key_envelope_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE;
ALTER TABLE public.conversation_key_envelope ADD CONSTRAINT conversation_key_envelope_recipient_user_id_fkey FOREIGN KEY (recipient_user_id) REFERENCES "user"(id) ON DELETE CASCADE;
ALTER TABLE public.conversation_key_envelope ADD CONSTRAINT conversation_key_envelope_sender_user_id_fkey FOREIGN KEY (sender_user_id) REFERENCES "user"(id) ON DELETE CASCADE;
ALTER TABLE public.conversation_participant ADD CONSTRAINT conversation_participant_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE;
ALTER TABLE public.conversation_participant ADD CONSTRAINT conversation_participant_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.document ADD CONSTRAINT document_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.document ADD CONSTRAINT document_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.document_reading_progress ADD CONSTRAINT document_reading_progress_document_id_fkey FOREIGN KEY (document_id) REFERENCES document(id);
ALTER TABLE public.document_reading_progress ADD CONSTRAINT document_reading_progress_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.flashcard_session ADD CONSTRAINT flashcard_session_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.flashcard_session ADD CONSTRAINT flashcard_session_generated_material_id_fkey FOREIGN KEY (generated_material_id) REFERENCES generated_material(id);
ALTER TABLE public.flashcard_session ADD CONSTRAINT flashcard_session_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.follow ADD CONSTRAINT follow_followed_id_fkey FOREIGN KEY (followed_id) REFERENCES "user"(id);
ALTER TABLE public.follow ADD CONSTRAINT follow_follower_id_fkey FOREIGN KEY (follower_id) REFERENCES "user"(id);
ALTER TABLE public.follow_request ADD CONSTRAINT follow_request_requester_id_fkey FOREIGN KEY (requester_id) REFERENCES "user"(id);
ALTER TABLE public.follow_request ADD CONSTRAINT follow_request_target_id_fkey FOREIGN KEY (target_id) REFERENCES "user"(id);
ALTER TABLE public.forum_post ADD CONSTRAINT forum_post_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.forum_reply ADD CONSTRAINT forum_reply_ai_answer_id_fkey FOREIGN KEY (ai_answer_id) REFERENCES ai_answer(id);
ALTER TABLE public.forum_reply ADD CONSTRAINT forum_reply_post_id_fkey FOREIGN KEY (post_id) REFERENCES forum_post(id) ON DELETE CASCADE;
ALTER TABLE public.forum_reply ADD CONSTRAINT forum_reply_triggered_by_user_id_fkey FOREIGN KEY (triggered_by_user_id) REFERENCES "user"(id);
ALTER TABLE public.forum_reply ADD CONSTRAINT forum_reply_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.generated_material ADD CONSTRAINT generated_material_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.generated_material ADD CONSTRAINT generated_material_flagged_by_fkey FOREIGN KEY (flagged_by) REFERENCES "user"(id);
ALTER TABLE public."group" ADD CONSTRAINT group_created_by_fkey FOREIGN KEY (created_by) REFERENCES "user"(id);
ALTER TABLE public."group" ADD CONSTRAINT group_program_id_fkey FOREIGN KEY (program_id) REFERENCES program(id);
ALTER TABLE public."group" ADD CONSTRAINT group_university_id_fkey FOREIGN KEY (university_id) REFERENCES university(id);
ALTER TABLE public.group_file ADD CONSTRAINT group_file_document_id_fkey FOREIGN KEY (document_id) REFERENCES document(id);
ALTER TABLE public.group_file ADD CONSTRAINT group_file_group_id_fkey FOREIGN KEY (group_id) REFERENCES "group"(id) ON DELETE CASCADE;
ALTER TABLE public.group_file ADD CONSTRAINT group_file_shared_by_user_id_fkey FOREIGN KEY (shared_by_user_id) REFERENCES "user"(id);
ALTER TABLE public.group_member ADD CONSTRAINT group_member_group_id_fkey FOREIGN KEY (group_id) REFERENCES "group"(id) ON DELETE CASCADE;
ALTER TABLE public.group_member ADD CONSTRAINT group_member_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.group_post ADD CONSTRAINT group_post_group_id_fkey FOREIGN KEY (group_id) REFERENCES "group"(id) ON DELETE CASCADE;
ALTER TABLE public.group_post ADD CONSTRAINT group_post_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.group_post_comment ADD CONSTRAINT group_post_comment_group_post_id_fkey FOREIGN KEY (group_post_id) REFERENCES group_post(id) ON DELETE CASCADE;
ALTER TABLE public.group_post_comment ADD CONSTRAINT group_post_comment_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.group_post_like ADD CONSTRAINT group_post_like_group_post_id_fkey FOREIGN KEY (group_post_id) REFERENCES group_post(id) ON DELETE CASCADE;
ALTER TABLE public.group_post_like ADD CONSTRAINT group_post_like_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.group_question_vote ADD CONSTRAINT group_question_vote_group_post_id_fkey FOREIGN KEY (group_post_id) REFERENCES group_post(id) ON DELETE CASCADE;
ALTER TABLE public.group_question_vote ADD CONSTRAINT group_question_vote_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.learning_event ADD CONSTRAINT learning_event_concept_id_fkey FOREIGN KEY (concept_id) REFERENCES learning_concept(id);
ALTER TABLE public.learning_event ADD CONSTRAINT learning_event_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.learning_event ADD CONSTRAINT learning_event_tutor_message_id_fkey FOREIGN KEY (tutor_message_id) REFERENCES tutor_message(id);
ALTER TABLE public.learning_event ADD CONSTRAINT learning_event_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.library_publication ADD CONSTRAINT library_publication_document_id_fkey FOREIGN KEY (document_id) REFERENCES document(id);
ALTER TABLE public.library_publication ADD CONSTRAINT library_publication_program_id_fkey FOREIGN KEY (program_id) REFERENCES program(id);
ALTER TABLE public.library_publication ADD CONSTRAINT library_publication_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id);
ALTER TABLE public.library_publication ADD CONSTRAINT library_publication_university_id_fkey FOREIGN KEY (university_id) REFERENCES university(id);
ALTER TABLE public.library_publication ADD CONSTRAINT library_publication_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.library_report ADD CONSTRAINT library_report_library_publication_id_fkey FOREIGN KEY (library_publication_id) REFERENCES library_publication(id);
ALTER TABLE public.library_report ADD CONSTRAINT library_report_reporter_user_id_fkey FOREIGN KEY (reporter_user_id) REFERENCES "user"(id);
ALTER TABLE public.library_report ADD CONSTRAINT library_report_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id);
ALTER TABLE public.message ADD CONSTRAINT message_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE;
ALTER TABLE public.message ADD CONSTRAINT message_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES "user"(id);
ALTER TABLE public.message_attachment ADD CONSTRAINT message_attachment_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE;
ALTER TABLE public.message_attachment ADD CONSTRAINT message_attachment_message_id_fkey FOREIGN KEY (message_id) REFERENCES message(id) ON DELETE CASCADE;
ALTER TABLE public.message_attachment ADD CONSTRAINT message_attachment_uploaded_by_user_id_fkey FOREIGN KEY (uploaded_by_user_id) REFERENCES "user"(id);
ALTER TABLE public.notification ADD CONSTRAINT notification_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.notification_preference ADD CONSTRAINT notification_preference_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.opportunity ADD CONSTRAINT opportunity_created_by_fkey FOREIGN KEY (created_by) REFERENCES "user"(id);
ALTER TABLE public.opportunity ADD CONSTRAINT opportunity_organisation_id_fkey FOREIGN KEY (organisation_id) REFERENCES organisation(id) ON DELETE CASCADE;
ALTER TABLE public.opportunity ADD CONSTRAINT opportunity_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id);
ALTER TABLE public.opportunity_promotion ADD CONSTRAINT opportunity_promotion_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunity(id) ON DELETE CASCADE;
ALTER TABLE public.opportunity_promotion ADD CONSTRAINT opportunity_promotion_organisation_id_fkey FOREIGN KEY (organisation_id) REFERENCES organisation(id);
ALTER TABLE public.opportunity_promotion ADD CONSTRAINT opportunity_promotion_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id);
ALTER TABLE public.organisation ADD CONSTRAINT organisation_created_by_fkey FOREIGN KEY (created_by) REFERENCES "user"(id);
ALTER TABLE public.organisation_member ADD CONSTRAINT organisation_member_organisation_id_fkey FOREIGN KEY (organisation_id) REFERENCES organisation(id) ON DELETE CASCADE;
ALTER TABLE public.organisation_member ADD CONSTRAINT organisation_member_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.payment ADD CONSTRAINT payment_content_item_id_fkey FOREIGN KEY (content_item_id) REFERENCES content_item(id);
ALTER TABLE public.payment ADD CONSTRAINT payment_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.program ADD CONSTRAINT program_university_id_fkey FOREIGN KEY (university_id) REFERENCES university(id);
ALTER TABLE public.push_subscription ADD CONSTRAINT push_subscription_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.quiz_attempt ADD CONSTRAINT quiz_attempt_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.quiz_attempt ADD CONSTRAINT quiz_attempt_generated_material_id_fkey FOREIGN KEY (generated_material_id) REFERENCES generated_material(id);
ALTER TABLE public.quiz_attempt ADD CONSTRAINT quiz_attempt_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.referral ADD CONSTRAINT referral_ambassador_id_fkey FOREIGN KEY (ambassador_id) REFERENCES ambassador(id);
ALTER TABLE public.referral ADD CONSTRAINT referral_first_payment_id_fkey FOREIGN KEY (first_payment_id) REFERENCES payment(id);
ALTER TABLE public.referral ADD CONSTRAINT referral_payout_id_fkey FOREIGN KEY (payout_id) REFERENCES ambassador_payout(id);
ALTER TABLE public.referral ADD CONSTRAINT referral_referred_user_id_fkey FOREIGN KEY (referred_user_id) REFERENCES "user"(id);
ALTER TABLE public.saved_library_material ADD CONSTRAINT saved_library_material_library_publication_id_fkey FOREIGN KEY (library_publication_id) REFERENCES library_publication(id);
ALTER TABLE public.saved_library_material ADD CONSTRAINT saved_library_material_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.saved_opportunity ADD CONSTRAINT saved_opportunity_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunity(id) ON DELETE CASCADE;
ALTER TABLE public.saved_opportunity ADD CONSTRAINT saved_opportunity_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.student_concept_mastery ADD CONSTRAINT student_concept_mastery_concept_id_fkey FOREIGN KEY (concept_id) REFERENCES learning_concept(id);
ALTER TABLE public.student_concept_mastery ADD CONSTRAINT student_concept_mastery_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.student_entitlement_usage ADD CONSTRAINT student_entitlement_usage_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES payment(id);
ALTER TABLE public.student_entitlement_usage ADD CONSTRAINT student_entitlement_usage_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.student_learning_profile ADD CONSTRAINT student_learning_profile_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.student_opportunity_discovery ADD CONSTRAINT student_opportunity_discovery_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE;
ALTER TABLE public.student_opportunity_discovery_audit ADD CONSTRAINT student_opportunity_discovery_audit_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE;
ALTER TABLE public.student_order ADD CONSTRAINT student_order_item_id_fkey FOREIGN KEY (item_id) REFERENCES content_item(id);
ALTER TABLE public.student_order ADD CONSTRAINT student_order_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES payment(id);
ALTER TABLE public.student_order ADD CONSTRAINT student_order_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.student_refund_request ADD CONSTRAINT student_refund_request_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES "user"(id);
ALTER TABLE public.student_refund_request ADD CONSTRAINT student_refund_request_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES payment(id);
ALTER TABLE public.student_refund_request ADD CONSTRAINT student_refund_request_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.student_subscription ADD CONSTRAINT student_subscription_initial_payment_id_fkey FOREIGN KEY (initial_payment_id) REFERENCES payment(id);
ALTER TABLE public.student_subscription ADD CONSTRAINT student_subscription_latest_payment_id_fkey FOREIGN KEY (latest_payment_id) REFERENCES payment(id);
ALTER TABLE public.student_subscription ADD CONSTRAINT student_subscription_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.study_activity_log ADD CONSTRAINT study_activity_log_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.study_activity_log ADD CONSTRAINT study_activity_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.study_friend_streak ADD CONSTRAINT study_friend_streak_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES "user"(id);
ALTER TABLE public.study_friend_streak ADD CONSTRAINT study_friend_streak_user_a_id_fkey FOREIGN KEY (user_a_id) REFERENCES "user"(id);
ALTER TABLE public.study_friend_streak ADD CONSTRAINT study_friend_streak_user_b_id_fkey FOREIGN KEY (user_b_id) REFERENCES "user"(id);
ALTER TABLE public.study_friend_streak_activity ADD CONSTRAINT study_friend_streak_activity_streak_id_fkey FOREIGN KEY (streak_id) REFERENCES study_friend_streak(id);
ALTER TABLE public.study_friend_streak_activity ADD CONSTRAINT study_friend_streak_activity_user_a_id_fkey FOREIGN KEY (user_a_id) REFERENCES "user"(id);
ALTER TABLE public.study_friend_streak_activity ADD CONSTRAINT study_friend_streak_activity_user_b_id_fkey FOREIGN KEY (user_b_id) REFERENCES "user"(id);
ALTER TABLE public.study_streak ADD CONSTRAINT study_streak_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.study_time_log ADD CONSTRAINT study_time_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.tutor_conversation ADD CONSTRAINT tutor_conversation_document_content_id_fkey FOREIGN KEY (document_content_id) REFERENCES document_content(id);
ALTER TABLE public.tutor_conversation ADD CONSTRAINT tutor_conversation_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.tutor_message ADD CONSTRAINT tutor_message_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES tutor_conversation(id) ON DELETE CASCADE;
ALTER TABLE public."user" ADD CONSTRAINT user_program_id_fkey FOREIGN KEY (program_id) REFERENCES program(id);
ALTER TABLE public."user" ADD CONSTRAINT user_university_id_fkey FOREIGN KEY (university_id) REFERENCES university(id);
ALTER TABLE public.user_achievement ADD CONSTRAINT user_achievement_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.user_key ADD CONSTRAINT user_key_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.user_warning ADD CONSTRAINT user_warning_content_report_id_fkey FOREIGN KEY (content_report_id) REFERENCES content_report(id);
ALTER TABLE public.user_warning ADD CONSTRAINT user_warning_issued_by_fkey FOREIGN KEY (issued_by) REFERENCES "user"(id);
ALTER TABLE public.user_warning ADD CONSTRAINT user_warning_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.view_progress ADD CONSTRAINT view_progress_content_item_id_fkey FOREIGN KEY (content_item_id) REFERENCES content_item(id);
ALTER TABLE public.view_progress ADD CONSTRAINT view_progress_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);
ALTER TABLE public.xp_event ADD CONSTRAINT xp_event_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id);

-- Non-constraint indexes
CREATE INDEX ix_ada_request_usage_user_created ON public.ada_request_usage USING btree (user_id, created_at);
CREATE INDEX idx_ai_answer_search_vector ON public.ai_answer USING gin (search_vector);
CREATE INDEX idx_ai_answer_question_trgm ON public.ai_answer USING gin (question_text gin_trgm_ops);
CREATE INDEX ix_ai_generation_artifact_content_feature ON public.ai_generation_artifact USING btree (content_hash, feature);
CREATE INDEX ix_ai_generation_artifact_status_updated ON public.ai_generation_artifact USING btree (status, updated_at);
CREATE INDEX ix_ai_generation_artifact_owner ON public.ai_generation_artifact USING btree (owner_user_id);
CREATE INDEX ix_ai_generation_inflight_artifact ON public.ai_generation_inflight USING btree (artifact_id);
CREATE INDEX ix_ai_generation_subscriber_family ON public.ai_generation_subscriber USING btree (base_fingerprint, status, created_at);
CREATE INDEX ix_ai_generation_variant_access_family ON public.ai_generation_variant_access USING btree (base_fingerprint, variant, status);
CREATE INDEX ix_ai_generation_variant_access_artifact ON public.ai_generation_variant_access USING btree (artifact_id);
CREATE INDEX ix_ai_generation_variant_artifact ON public.ai_generation_variant_access USING btree (artifact_id);
CREATE INDEX ix_ai_job_status ON public.ai_job USING btree (status);
CREATE INDEX ix_ai_job_document_content_id ON public.ai_job USING btree (document_content_id);
CREATE INDEX ix_ai_job_claimed_worker_id ON public.ai_job USING btree (claimed_worker_id) WHERE (claimed_worker_id IS NOT NULL);
CREATE INDEX idx_ai_usage_log_user_created ON public.ai_usage_log USING btree (user_id, created_at DESC);
CREATE INDEX idx_ai_usage_log_created ON public.ai_usage_log USING btree (created_at);
CREATE INDEX ix_auth_otp_user_purpose_created ON public.auth_otp USING btree (user_id, purpose, created_at DESC);
CREATE INDEX ix_auth_otp_target_created ON public.auth_otp USING btree (target, purpose, created_at DESC);
CREATE INDEX ix_auth_otp_ip_created ON public.auth_otp USING btree (request_ip, purpose, created_at DESC);
CREATE INDEX ix_b2b_audit_campaign_created ON public.b2b_audit_log USING btree (campaign_id, created_at DESC);
CREATE INDEX ix_b2b_campaign_funding_campaign ON public.b2b_campaign_funding USING btree (campaign_id, created_at DESC);
CREATE INDEX ix_b2b_campaign_ledger_campaign_created ON public.b2b_campaign_ledger USING btree (campaign_id, created_at DESC);
CREATE INDEX ix_b2b_campaign_ledger_payment ON public.b2b_campaign_ledger USING btree (payment_id);
CREATE INDEX ix_b2b_invoice_org_created ON public.b2b_invoice USING btree (organisation_id, created_at DESC);
CREATE INDEX ix_b2b_payment_org_created ON public.b2b_payment USING btree (organisation_id, created_at DESC);
CREATE INDEX ix_b2b_payment_campaign_created ON public.b2b_payment USING btree (campaign_id, created_at DESC);
CREATE INDEX ix_b2b_payment_refund_reference ON public.b2b_payment USING btree (refund_reference);
CREATE INDEX ix_b2b_payment_refund_status ON public.b2b_payment USING btree (refund_status);
CREATE UNIQUE INDEX ix_chat_message_idempotency_message ON public.chat_message_idempotency USING btree (message_id);
CREATE INDEX ix_chat_message_meta_conversation_kind ON public.chat_message_meta USING btree (conversation_id, kind);
CREATE INDEX ix_chat_message_receipt_user_delivery ON public.chat_message_receipt USING btree (user_id, delivered_at);
CREATE INDEX ix_chat_message_receipt_message_delivery ON public.chat_message_receipt USING btree (message_id, delivered_at);
CREATE INDEX ix_concept_prerequisite_concept ON public.concept_prerequisite USING btree (concept_id);
CREATE INDEX ix_content_report_status ON public.content_report USING btree (status);
CREATE INDEX ix_conversation_key_envelope_conversation ON public.conversation_key_envelope USING btree (conversation_id, key_epoch);
CREATE INDEX ix_conversation_key_envelope_recipient ON public.conversation_key_envelope USING btree (recipient_user_id, conversation_id, key_epoch);
CREATE INDEX ix_discovery_event_campaign_created ON public.discovery_event USING btree (campaign_id, created_at);
CREATE INDEX ix_discovery_event_user_type_created ON public.discovery_event USING btree (user_id, event_type, created_at);
CREATE INDEX ix_document_user_last_opened ON public.document USING btree (user_id, last_opened_at DESC, id DESC);
CREATE INDEX ix_document_reading_progress_user_id ON public.document_reading_progress USING btree (user_id);
CREATE INDEX ix_document_reading_progress_document_id ON public.document_reading_progress USING btree (document_id);
CREATE INDEX ix_flashcard_session_user ON public.flashcard_session USING btree (user_id);
CREATE INDEX idx_forum_post_user ON public.forum_post USING btree (user_id);
CREATE INDEX idx_forum_reply_post_created ON public.forum_reply USING btree (post_id, created_at);
CREATE INDEX idx_forum_reply_ai_answer ON public.forum_reply USING btree (ai_answer_id);
CREATE UNIQUE INDEX uq_generated_material_fingerprint ON public.generated_material USING btree (generation_fingerprint);
CREATE INDEX ix_generated_material_content_type ON public.generated_material USING btree (document_content_id, material_type);
CREATE INDEX ix_generated_material_owner ON public.generated_material USING btree (owner_user_id);
CREATE INDEX ix_kokoro_gpu_scaling_decisions_created ON public.kokoro_gpu_scaling_decisions USING btree (created_at DESC);
CREATE INDEX ix_kokoro_gpu_scaling_decisions_action ON public.kokoro_gpu_scaling_decisions USING btree (action, created_at DESC);
CREATE INDEX ix_kokoro_gpu_workers_status ON public.kokoro_gpu_workers USING btree (status);
CREATE INDEX ix_kokoro_gpu_workers_heartbeat ON public.kokoro_gpu_workers USING btree (last_heartbeat_at);
CREATE UNIQUE INDEX uq_kokoro_gpu_workers_worker_id ON public.kokoro_gpu_workers USING btree (worker_id) WHERE (worker_id IS NOT NULL);
CREATE INDEX ix_library_publication_academic_context ON public.library_publication USING btree (university_id, program_id, year, semester, status);
CREATE INDEX ix_message_conversation_e2ee_epoch ON public.message USING btree (conversation_id, e2ee_key_epoch, created_at);
CREATE INDEX ix_opp_view_event_opp_created ON public.opportunity_view_event USING btree (opportunity_id, created_at);
CREATE INDEX ix_opp_view_event_user_opp ON public.opportunity_view_event USING btree (user_id, opportunity_id, created_at);
CREATE INDEX ix_org_kyc_org_status ON public.organisation_kyc_document USING btree (organisation_id, status, created_at DESC);
CREATE INDEX ix_payment_subscription_entitlement_period ON public.payment USING btree (user_id, payment_type, status, subscription_starts_at, subscription_expires_at);
CREATE INDEX ix_product_activity_day_date_user ON public.product_activity_day USING btree (activity_date, user_id);
CREATE INDEX ix_quiz_attempt_user ON public.quiz_attempt USING btree (user_id);
CREATE INDEX ix_concept_mastery_user ON public.student_concept_mastery USING btree (user_id);
CREATE INDEX ix_student_entitlement_usage_payment ON public.student_entitlement_usage USING btree (payment_id, created_at);
CREATE INDEX ix_student_entitlement_usage_user_created ON public.student_entitlement_usage USING btree (user_id, created_at);
CREATE INDEX ix_student_opportunity_discovery_audit_user_created ON public.student_opportunity_discovery USING btree (user_id, updated_at);
CREATE INDEX ix_student_opportunity_discovery_audit_log_user_created ON public.student_opportunity_discovery_audit USING btree (user_id, created_at);
CREATE INDEX ix_student_order_user_created ON public.student_order USING btree (user_id, created_at DESC);
CREATE INDEX ix_student_order_status ON public.student_order USING btree (status);
CREATE INDEX ix_student_order_item ON public.student_order USING btree (item_id);
CREATE INDEX ix_student_refund_request_user ON public.student_refund_request USING btree (user_id, requested_at);
CREATE INDEX ix_student_subscription_user_status ON public.student_subscription USING btree (user_id, status);
CREATE INDEX ix_study_activity_log_user_date ON public.study_activity_log USING btree (user_id, activity_date);
CREATE INDEX ix_study_friend_streak_a ON public.study_friend_streak USING btree (user_a_id, status);
CREATE INDEX ix_study_friend_streak_b ON public.study_friend_streak USING btree (user_b_id, status);
CREATE INDEX ix_study_friend_streak_activity_date ON public.study_friend_streak_activity USING btree (activity_date);
CREATE INDEX ix_user_warning_user_id ON public.user_warning USING btree (user_id);

-- Application-owned public functions
CREATE OR REPLACE FUNCTION public.prepza_default_new_conversation_e2ee()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
    IF NEW.is_group = TRUE THEN
        NEW.e2ee_mode := 'group_v1';
        NEW.key_epoch := 1;
    ELSE
        NEW.e2ee_mode := 'direct_v1';
        NEW.key_epoch := 0;
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.prepza_default_new_group_e2ee()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
    IF NEW.is_group = TRUE THEN
        NEW.e2ee_mode := 'group_v1';
        NEW.key_epoch := 1;
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.prepza_nairobi_date(ts timestamp with time zone DEFAULT CURRENT_TIMESTAMP)
 RETURNS date
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog'
AS $function$
  SELECT (ts AT TIME ZONE 'Africa/Nairobi')::date;
$function$;

-- Application triggers
CREATE TRIGGER trg_prepza_default_new_conversation_e2ee BEFORE INSERT ON public.conversation FOR EACH ROW EXECUTE FUNCTION prepza_default_new_conversation_e2ee();
