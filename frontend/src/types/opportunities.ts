type OpportunityOrg = { id: number; name: string; logo_url: string | null; website: string | null }
type OpportunityPublic = {
  id: number
  title: string
  description: string
  opportunity_type: string
  location: string | null
  is_remote: boolean
  application_url: string | null
  application_instructions: string | null
  application_deadline: string | null
  expiry_date: string | null
  published_at: string | null
  view_count: number
  organisation: OpportunityOrg | null
  promotion_type: string | null
  saved: boolean
}

type SponsoredCampaign = {
  campaign_id: number
  organisation_id: number
  opportunity_id: number | null
  name: string
  objective: string
  placement: string
  featured: boolean
  opportunity: OpportunityPublic
}
