"""B2B organisation portal: dashboard, opportunity analytics, free distribution caps and billing documents."""
from __future__ import annotations
import io, uuid
from datetime import datetime
from flask import jsonify, request, session, send_file
from sqlalchemy import text
import fitz

FREE_ORGANIC_IMPRESSION_CAP = 5000
FREE_ORGANIC_PER_STUDENT_CAP = 3
CAMPAIGN_MAX_DAYS = (7, 30, 90)

def register_b2b_organisation_portal(app, db):
    db.session.execute(text("""
      ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS organic_free_impression_cap INTEGER NOT NULL DEFAULT 5000;
      ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS organic_free_cap_reached_at TIMESTAMP;
    """))
    db.session.execute(text("""
      CREATE TABLE IF NOT EXISTS opportunity_view_event (
        id BIGSERIAL PRIMARY KEY, opportunity_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        source VARCHAR(20) NOT NULL DEFAULT 'organic', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
      CREATE INDEX IF NOT EXISTS ix_opp_view_event_opp_created ON opportunity_view_event(opportunity_id,created_at);
      CREATE INDEX IF NOT EXISTS ix_opp_view_event_user_opp ON opportunity_view_event(user_id,opportunity_id,created_at);
      CREATE TABLE IF NOT EXISTS organisation_kyc_document (
        id BIGSERIAL PRIMARY KEY, organisation_id INTEGER NOT NULL, document_type VARCHAR(60) NOT NULL,
        file_name VARCHAR(255), storage_path TEXT, status VARCHAR(30) NOT NULL DEFAULT 'pending',
        admin_notes TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_at TIMESTAMP, reviewed_by INTEGER
      );
      CREATE TABLE IF NOT EXISTS b2b_invoice (
        id BIGSERIAL PRIMARY KEY, organisation_id INTEGER NOT NULL, campaign_id BIGINT,
        invoice_number VARCHAR(80) NOT NULL UNIQUE, currency VARCHAR(3) NOT NULL DEFAULT 'KES',
        subtotal_minor BIGINT NOT NULL, processing_fee_minor BIGINT NOT NULL DEFAULT 0,
        total_minor BIGINT NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'issued',
        payment_method VARCHAR(30) NOT NULL DEFAULT 'bank_transfer', due_at TIMESTAMP,
        paid_at TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
      CREATE INDEX IF NOT EXISTS ix_b2b_invoice_org_created ON b2b_invoice(organisation_id,created_at DESC);
    """))
    db.session.commit()

    def role(oid,uid):
        return db.session.execute(text("SELECT role FROM organisation_member WHERE organisation_id=:o AND user_id=:u LIMIT 1"),{"o":oid,"u":uid}).scalar_one_or_none()
    def access(oid,uid,owner=False):
        r=role(oid,uid); return r=="owner" if owner else r in ("owner","manager")
    def csrf():
        return bool(session.get("csrf_token") and request.headers.get("X-CSRF-Token")==session.get("csrf_token"))

    @app.get("/api/organisations/<int:oid>/portal/dashboard")
    def portal_dashboard(oid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid): return jsonify({"error":"Organisation membership required"}),403
        org=db.session.execute(text("SELECT id,name,description,website,logo_url,contact_email,contact_phone,verification_status,verification_notes,is_active FROM organisation WHERE id=:o"),{"o":oid}).mappings().first()
        if not org:return jsonify({"error":"Organisation not found"}),404
        plan=db.session.execute(text("SELECT plan_code,status,monthly_fee_kes,active_user_cap,started_at,expires_at FROM organisation_billing WHERE organisation_id=:o"),{"o":oid}).mappings().first()
        opps=db.session.execute(text("""
          SELECT o.id,o.title,o.status,o.view_count,o.organic_free_impression_cap,o.organic_free_cap_reached_at,
                 o.application_deadline,o.expiry_date,
                 COALESCE(SUM(c.delivered_impressions),0) sponsored_impressions,
                 COALESCE(SUM(c.delivered_clicks),0) sponsored_clicks,
                 COALESCE(SUM(c.delivered_applications),0) sponsored_applications
          FROM opportunity o LEFT JOIN discovery_campaign c ON c.opportunity_id=o.id AND c.organisation_id=:o
          WHERE o.organisation_id=:o GROUP BY o.id ORDER BY o.created_at DESC LIMIT 100
        """),{"o":oid}).mappings().all()
        camps=db.session.execute(text("""
          SELECT c.id,c.opportunity_id,c.name,c.objective,c.placement,c.status,c.budget_kes,
                 c.delivered_impressions,c.delivered_clicks,c.delivered_applications,c.push_delivered,
                 c.funded_amount_minor,c.starts_at,c.ends_at,COALESCE(o.title,c.name) opportunity_title
          FROM discovery_campaign c LEFT JOIN opportunity o ON o.id=c.opportunity_id
          WHERE c.organisation_id=:o ORDER BY c.created_at DESC LIMIT 100
        """),{"o":oid}).mappings().all()
        funded=db.session.execute(text("SELECT COALESCE(SUM(signed_amount_minor),0) FROM b2b_campaign_ledger l JOIN discovery_campaign c ON c.id=l.campaign_id WHERE c.organisation_id=:o AND l.entry_type='funding'"),{"o":oid}).scalar_one() or 0
        spent=db.session.execute(text("SELECT COALESCE(SUM(-signed_amount_minor),0) FROM b2b_campaign_ledger l JOIN discovery_campaign c ON c.id=l.campaign_id WHERE c.organisation_id=:o AND l.entry_type IN ('impression','click','push_delivery')"),{"o":oid}).scalar_one() or 0
        return jsonify({"organisation":dict(org),"plan":dict(plan) if plan else {"plan_code":"launch","status":"trial","monthly_fee_kes":2500},
          "ad_budget":{"funded_minor":int(funded),"spent_minor":int(spent),"available_minor":max(0,int(funded)-int(spent))},
          "active_sponsorships":sum(1 for c in camps if c["status"] in ("active","paused")),
          "opportunities":[dict(x) for x in opps],"campaigns":[dict(x) for x in camps],
          "free_policy":{"impression_cap":5000,"per_student_cap":3}})

    @app.get("/api/organisations/<int:oid>/portal/opportunities/<int:opp_id>/analytics")
    def opportunity_analytics(oid,opp_id):
        uid=session.get("user_id")
        if not uid or not access(oid,uid):return jsonify({"error":"Organisation membership required"}),403
        opp=db.session.execute(text("SELECT id,title,status,view_count,organic_free_impression_cap,organic_free_cap_reached_at FROM opportunity WHERE id=:i AND organisation_id=:o"),{"i":opp_id,"o":oid}).mappings().first()
        if not opp:return jsonify({"error":"Opportunity not found"}),404
        organic=db.session.execute(text("SELECT COUNT(*) impressions,COUNT(DISTINCT user_id) reach FROM opportunity_view_event WHERE opportunity_id=:i AND source='organic'"),{"i":opp_id}).mappings().first()
        camps=db.session.execute(text("""
          SELECT id,name,status,objective,placement,budget_kes,funded_amount_minor,delivered_impressions,
                 delivered_clicks,delivered_applications,push_delivered,starts_at,ends_at
          FROM discovery_campaign WHERE organisation_id=:o AND opportunity_id=:i ORDER BY created_at DESC
        """),{"o":oid,"i":opp_id}).mappings().all()
        return jsonify({"opportunity":dict(opp),"organic":{"impressions":int(organic["impressions"]),"reach":int(organic["reach"])},
          "sponsored":{"impressions":sum(int(c["delivered_impressions"] or 0) for c in camps),"clicks":sum(int(c["delivered_clicks"] or 0) for c in camps),"applications":sum(int(c["delivered_applications"] or 0) for c in camps),"push_deliveries":sum(int(c["push_delivered"] or 0) for c in camps)},
          "campaigns":[dict(c) for c in camps]})

    @app.get("/api/organisations/<int:oid>/portal/campaigns/<int:cid>/analytics")
    def campaign_analytics(oid,cid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid):return jsonify({"error":"Organisation membership required"}),403
        c=db.session.execute(text("SELECT c.*,COALESCE(o.title,c.name) opportunity_title FROM discovery_campaign c LEFT JOIN opportunity o ON o.id=c.opportunity_id WHERE c.id=:i AND c.organisation_id=:o"),{"i":cid,"o":oid}).mappings().first()
        if not c:return jsonify({"error":"Campaign not found"}),404
        daily=db.session.execute(text("""
          SELECT DATE(created_at) day,COUNT(*) FILTER(WHERE event_type='impression') impressions,
                 COUNT(*) FILTER(WHERE event_type='click') clicks,COUNT(*) FILTER(WHERE event_type='application') applications
          FROM discovery_event WHERE campaign_id=:i GROUP BY DATE(created_at) ORDER BY day
        """),{"i":cid}).mappings().all()
        return jsonify({"campaign":dict(c),"daily":[dict(x) for x in daily]})

    @app.post("/api/opportunities/<int:opp_id>/organic-view")
    def record_organic_view(opp_id):
        uid=session.get("user_id")
        if not uid:return jsonify({"error":"Not logged in"}),401
        row=db.session.execute(text("""
          SELECT o.*,org.name organisation_name,org.logo_url,org.website,org.verification_status,org.is_active
          FROM opportunity o JOIN organisation org ON org.id=o.organisation_id WHERE o.id=:i FOR UPDATE
        """),{"i":opp_id}).mappings().first()
        if not row or row["status"]!="published" or row["verification_status"]!="verified" or not row["is_active"] or row["expiry_date"]<=datetime.utcnow():
            db.session.rollback();return jsonify({"error":"Opportunity not found"}),404
        paid=db.session.execute(text("SELECT 1 FROM discovery_campaign WHERE opportunity_id=:i AND organisation_id=:o AND status='active' LIMIT 1"),{"i":opp_id,"o":row["organisation_id"]}).first()
        total=db.session.execute(text("SELECT COUNT(*) FROM opportunity_view_event WHERE opportunity_id=:i AND source='organic'"),{"i":opp_id}).scalar_one()
        mine=db.session.execute(text("SELECT COUNT(*) FROM opportunity_view_event WHERE opportunity_id=:i AND user_id=:u AND source='organic'"),{"i":opp_id,"u":uid}).scalar_one()
        if row["organic_free_cap_reached_at"] and not paid:
            db.session.rollback();return jsonify({"error":"This opportunity has reached its free 5,000-view limit.","cap_reached":True}),410
        if not paid and int(total)>=5000:
            db.session.execute(text("UPDATE opportunity SET organic_free_cap_reached_at=COALESCE(organic_free_cap_reached_at,CURRENT_TIMESTAMP) WHERE id=:i"),{"i":opp_id});db.session.commit()
            return jsonify({"error":"This opportunity has reached its free 5,000-view limit.","cap_reached":True}),410
        if not paid and int(mine)>=3:
            db.session.rollback();return jsonify({"error":"Your free views for this opportunity have been used."}),429
        db.session.execute(text("INSERT INTO opportunity_view_event(opportunity_id,user_id,source) VALUES(:i,:u,'organic')"),{"i":opp_id,"u":uid})
        db.session.execute(text("UPDATE opportunity SET view_count=view_count+1 WHERE id=:i"),{"i":opp_id})
        if not paid and int(total)+1>=5000:db.session.execute(text("UPDATE opportunity SET organic_free_cap_reached_at=CURRENT_TIMESTAMP WHERE id=:i"),{"i":opp_id})
        db.session.commit()
        saved=False
        try:saved=bool(db.session.execute(text("SELECT 1 FROM saved_opportunity WHERE opportunity_id=:i AND user_id=:u LIMIT 1"),{"i":opp_id,"u":uid}).first())
        except Exception:db.session.rollback()
        return jsonify({"ok":True,"organic_impressions":int(total)+1,"organic_reach":int(db.session.execute(text("SELECT COUNT(DISTINCT user_id) FROM opportunity_view_event WHERE opportunity_id=:i AND source='organic'"),{"i":opp_id}).scalar_one()),"cap":5000,"saved":saved,
          "opportunity":{"id":row["id"],"title":row["title"],"description":row["description"],"opportunity_type":row["opportunity_type"],"location":row["location"],"is_remote":row["is_remote"],"application_url":row["application_url"],"application_instructions":row["application_instructions"],"application_deadline":row["application_deadline"].isoformat() if row["application_deadline"] else None,"expiry_date":row["expiry_date"].isoformat() if row["expiry_date"] else None,"published_at":row["published_at"].isoformat() if row["published_at"] else None,"view_count":row["view_count"]+1,"organisation":{"id":row["organisation_id"],"name":row["organisation_name"],"logo_url":row["logo_url"],"website":row["website"]},"promotion_type":None,"saved":saved}})

    @app.get("/api/organisations/<int:oid>/billing/payments")
    def org_billing(oid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid):return jsonify({"error":"Organisation membership required"}),403
        p=db.session.execute(text("SELECT id,provider,provider_reference,currency,customer_amount_minor,campaign_amount_minor,processing_fee_minor,status,purpose,paid_at,created_at FROM b2b_payment WHERE organisation_id=:o ORDER BY created_at DESC LIMIT 200"),{"o":oid}).mappings().all()
        i=db.session.execute(text("SELECT id,invoice_number,campaign_id,currency,subtotal_minor,processing_fee_minor,total_minor,status,payment_method,due_at,paid_at,created_at FROM b2b_invoice WHERE organisation_id=:o ORDER BY created_at DESC LIMIT 100"),{"o":oid}).mappings().all()
        return jsonify({"payments":[dict(x) for x in p],"invoices":[dict(x) for x in i]})

    @app.post("/api/organisations/<int:oid>/discovery/campaigns/<int:cid>/invoice")
    def create_invoice(oid,cid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid,owner=True) or not csrf():return jsonify({"error":"Organisation owner and valid CSRF token required"}),403
        c=db.session.execute(text("SELECT id,budget_kes,funding_status FROM discovery_campaign WHERE id=:i AND organisation_id=:o"),{"i":cid,"o":oid}).mappings().first()
        if not c:return jsonify({"error":"Campaign not found"}),404
        if c["funding_status"] in ("funded","credited"):return jsonify({"error":"Campaign is already funded"}),409
        number="PZ-"+datetime.utcnow().strftime("%Y%m%d")+"-"+uuid.uuid4().hex[:8].upper()
        amount=int(c["budget_kes"])*100
        db.session.execute(text("""INSERT INTO b2b_invoice(organisation_id,campaign_id,invoice_number,subtotal_minor,total_minor,status,payment_method,due_at)
          VALUES(:o,:c,:n,:a,:a,'issued','bank_transfer',CURRENT_TIMESTAMP+INTERVAL '14 days')"""),{"o":oid,"c":cid,"n":number,"a":amount})
        db.session.execute(text("UPDATE discovery_campaign SET status='pending_payment',updated_at=CURRENT_TIMESTAMP WHERE id=:i"),{"i":cid})
        db.session.commit()
        return jsonify({"ok":True,"invoice_number":number,"amount_minor":amount,"status":"issued"}),201

    def pdf(title,ref,org,campaign,amount,status,filename):
        doc=fitz.open();page=doc.new_page();y=65
        page.insert_text((55,y),title,fontsize=20,color=(0.04,0.08,0.22));y+=35
        for k,v in [("Organisation",org),("Reference",ref),("Campaign",campaign or "—"),("Amount",f"KES {int(amount)/100:,.2f}"),("Status",status),("Issued",datetime.utcnow().strftime("%d %b %Y %H:%M UTC"))]:
            page.insert_text((55,y),f"{k}: {v or '—'}",fontsize=11);y+=23
        page.insert_text((55,y+12),"Prepza Education · Customer payment record",fontsize=9,color=(0.35,0.38,0.45))
        data=doc.tobytes();doc.close()
        return send_file(io.BytesIO(data),mimetype="application/pdf",as_attachment=True,download_name=filename)

    @app.get("/api/organisations/<int:oid>/billing/invoices/<int:iid>/receipt.pdf")
    def invoice_pdf(oid,iid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid):return jsonify({"error":"Organisation membership required"}),403
        x=db.session.execute(text("SELECT i.*,o.name organisation_name,c.name campaign_name FROM b2b_invoice i JOIN organisation o ON o.id=i.organisation_id LEFT JOIN discovery_campaign c ON c.id=i.campaign_id WHERE i.id=:i AND i.organisation_id=:o"),{"i":iid,"o":oid}).mappings().first()
        if not x:return jsonify({"error":"Invoice not found"}),404
        return pdf("PREPZA INVOICE",x["invoice_number"],x["organisation_name"],x["campaign_name"],x["total_minor"],str(x["status"]).upper(),"invoice-"+x["invoice_number"]+".pdf")

    @app.get("/api/organisations/<int:oid>/billing/payments/<int:pid>/receipt.pdf")
    def payment_pdf(oid,pid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid):return jsonify({"error":"Organisation membership required"}),403
        x=db.session.execute(text("SELECT p.*,o.name organisation_name,c.name campaign_name FROM b2b_payment p JOIN organisation o ON o.id=p.organisation_id LEFT JOIN discovery_campaign c ON c.id=p.campaign_id WHERE p.id=:i AND p.organisation_id=:o"),{"i":pid,"o":oid}).mappings().first()
        if not x:return jsonify({"error":"Payment not found"}),404
        return pdf("PREPZA PAYMENT RECEIPT",x["provider_reference"],x["organisation_name"],x["campaign_name"],x["customer_amount_minor"],str(x["status"]).upper(),"receipt-"+x["provider_reference"]+".pdf")

    @app.post("/api/organisations/<int:oid>/kyc/upload")
    def kyc_upload(oid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid,owner=True) or not csrf(): return jsonify({"error":"Organisation owner and valid CSRF token required"}),403
        file=request.files.get("file")
        dtype=str(request.form.get("document_type") or "").strip()[:60]
        if not file or not file.filename or not dtype: return jsonify({"error":"Document type and file are required"}),400
        allowed={"pdf","png","jpg","jpeg"}
        ext=file.filename.rsplit(".",1)[-1].lower() if "." in file.filename else ""
        if ext not in allowed:return jsonify({"error":"KYC documents must be PDF, PNG or JPEG"}),400
        data=file.read()
        if len(data)>10*1024*1024:return jsonify({"error":"KYC document must be 10 MB or smaller"}),400
        base=os.environ.get("SUPABASE_URL","").strip()
        key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","").strip()
        if not base or not key:return jsonify({"error":"Private document storage is not configured yet"}),503
        bucket="organisation-kyc"
        headers={"Authorization":"Bearer "+key,"apikey":key,"Content-Type":file.mimetype or "application/octet-stream"}
        try:
            requests.post(base+"/storage/v1/bucket",json={"id":bucket,"name":bucket,"public":False},headers={"Authorization":"Bearer "+key,"apikey":key},timeout=10)
        except Exception: pass
        path=f"{oid}/{uuid.uuid4().hex}.{ext}"
        res=requests.post(base+"/storage/v1/object/"+bucket+"/"+path,data=data,headers=headers,timeout=30)
        if not res.ok:return jsonify({"error":"Could not securely store the KYC document"}),502
        db.session.execute(text("INSERT INTO organisation_kyc_document(organisation_id,document_type,file_name,storage_path) VALUES(:o,:t,:f,:p)"),{"o":oid,"t":dtype,"f":file.filename[:255],"p":path})
        db.session.commit()
        return jsonify({"ok":True,"status":"pending","file_name":file.filename[:255]}),201

    @app.get("/api/organisations/<int:oid>/kyc")
    def kyc_list(oid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid):return jsonify({"error":"Organisation membership required"}),403
        rows=db.session.execute(text("SELECT id,document_type,file_name,status,admin_notes,created_at,reviewed_at FROM organisation_kyc_document WHERE organisation_id=:o ORDER BY created_at DESC"),{"o":oid}).mappings().all()
        return jsonify({"documents":[dict(x) for x in rows]})

    @app.post("/api/organisations/<int:oid>/kyc")
    def kyc_submit(oid):
        uid=session.get("user_id")
        if not uid or not access(oid,uid,owner=True) or not csrf():return jsonify({"error":"Organisation owner and valid CSRF token required"}),403
        data=request.get_json(silent=True) or {}
        dtype=str(data.get("document_type") or "").strip()[:60];fname=str(data.get("file_name") or "").strip()[:255];path=str(data.get("storage_path") or "").strip()[:500]
        if not dtype or not fname or not path:return jsonify({"error":"document_type, file_name and storage_path are required"}),400
        db.session.execute(text("INSERT INTO organisation_kyc_document(organisation_id,document_type,file_name,storage_path) VALUES(:o,:t,:f,:p)"),{"o":oid,"t":dtype,"f":fname,"p":path});db.session.commit()
        return jsonify({"ok":True,"status":"pending"}),201
