export interface SessionUser {
  username: string;
}

export interface SessionResponse {
  authenticated: boolean;
  user: SessionUser | null;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface TopicFilter {
  code: string;
  label: string;
}

export interface NewsArticle {
  title: string;
  source: string;
  published: string | null;
  link: string;
  topic: string;
  topic_code: string;
  summary: string | null;
  image_url: string | null;
}

export interface NewsResponse {
  generated_at: string;
  timezone_name: string;
  selected_topics: string[];
  has_selected_topics: boolean;
  matched_source_count: number;
  warnings: string[];
  topic_filters: TopicFilter[];
  active_topic: string;
  selected_topic_label: string;
  newsletter_enabled: boolean;
  newsletter_time: string | null;
  email_verified: boolean;
  articles: NewsArticle[];
}

export interface NewsletterPreviewResponse {
  generated_at: string;
  timezone_name: string;
  newsletter_enabled: boolean;
  selected_topics: string[];
  has_selected_topics: boolean;
  matched_source_count: number;
  warnings: string[];
  email_verified: boolean;
  articles: NewsArticle[];
}

export interface NewsletterAttempt {
  id: number;
  created_at: string;
  recipient: string;
  status: string;
  status_label: string;
}

export interface NewsletterHistoryResponse {
  timezone_name: string;
  attempts: NewsletterAttempt[];
}

export interface NewsletterSendResponse {
  status: string;
  detail: string;
  attempt?: NewsletterAttempt;
}

export interface ApiErrorResponse {
  detail?: string;
  message?: string;
  field_errors?: Record<string, string[]>;
  non_field_errors?: string[];
}

export interface RegistrationPayload {
  username: string;
  email: string;
  password1: string;
  password2: string;
}

export interface RegistrationResponse {
  created: boolean;
  email_status: string;
  message: string;
}

export interface VerificationResponse {
  state: 'confirm' | 'verified' | 'already_verified' | 'invalid';
  email: string | null;
  message: string | null;
}

export interface TopicChoice {
  code: string;
  label: string;
}

export interface Preferences {
  newsletter_topics: string[];
  newsletter_enabled: boolean;
  newsletter_time: string;
  timezone_name: string;
  alerts_enabled: boolean;
  alert_topics: string[];
  daily_alert_limit: number;
}

export interface PreferencesResponse {
  email: string;
  email_verified_at: string | null;
  preferences: Preferences;
  topic_choices: TopicChoice[];
  field_labels: Record<string, string>;
}
