from datetime import datetime
from flask import jsonify, request, session
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

OPPORTUNITY_TYPES=("job","internship","scholarship","competition","volunteering","event","other")
PAGE_SIZE=20

def register_opportunity_runtime(app,db,Opportunity,Organisation,User,OrganisationMember,require_csrf):
    class SavedOpportunity(db.Model):
        __tablename__="saved_opportunity"
        id=db.Column(db.Integer,primary_key=True)
        user_id=db.Column(db.Integer,db.ForeignKey("user.id",ondelete="CASCADE"),nullable=False)
        opportunity_id=db.Column(db.Integer,db.ForeignKey("opportunity.id",ondelete="CASCADE"),nullable=False)
        created_at=db.Column(db.DateTime,default=datetime.utcnow)
        __table_args__=(db.UniqueConstraint("user_id","opportunity_id",name="uq_saved_opportunity_user_opp"),)

    class OpportunityUniversityTarget(db.Model):
        __tablename__="opportunity_university_target"
        id=db.Column(db.Integer,primary_key=True)
        opportunity_id=db.Column(db.Integer,db.ForeignKey("opportunity.id",ondelete="CASCADE"),nullable=False)
        university_id=db.Column(db.Integer,db.ForeignKey("university.id",ondelete="CASCADE"),nullable=False)
        __table_args__=(db.UniqueConstraint("opportunity_id","university_id",name="uq_opp_university_target"),)

    class OpportunityProgramTarget(db.Model):
        __tablename__="opportunity_program_target"
        id=db.Column(db.Integer,primary_key=True)
        opportunity_id=db.Column(db.Integer,db.ForeignKey("opportunity.id",ondelete="CASCADE"),nullable=False)
        program_id=db.Column(db.Integer,db.ForeignKey("program.id",ondelete="CASCADE"),nullable=False)
        __table_args__=(db.UniqueConstraint("opportunity_id","program_id",name="uq_opp_program_target"),)

    class OpportunityYearTarget(db.Model):
        __tablename__="opportunity_year_target"
        id=db.Column(db.Integer,primary_key=True)
        opportunity_id=db.Column(db.Integer,db.ForeignKey("opportunity.id",ondelete="CASCADE"),nullable=False)
        year=db.Column(db.Integer,nullable=False)
        __table_args__=(db.UniqueConstraint("opportunity_id","year",name="uq_opp_year_target"),)

    class OpportunitySemesterTarget(db.Model):
        __tablename__="opportunity_semester_target"
        id=db.Column(db.Integer,primary_key=True)
        opportunity_id=db.Column(db.Integer,db.ForeignKey("opportunity.id",ondelete="CASCADE"),nullable=False)
        semester=db.Column(db.Integer,nullable=False)
        __table_args__=(db.UniqueConstraint("opportunity_id","semester",name="uq_opp_semester_target"),)

    def targeting(opp):
        return {
          "university_ids":[r.university_id for r in OpportunityUniversityTarget.query.filter_by(opportunity_id=opp.id).all()],
          "program_ids":[r.program_id for r in OpportunityProgramTarget.query.filter_by(opportunity_id=opp.id).all()],
          "years":[r.year for r in OpportunityYearTarget.query.filter_by(opportunity_id=opp.id).all()],
          "semesters":[r.semester for r in OpportunitySemesterTarget.query.filter_by(opportunity_id=opp.id).all()],
        }

    def set_targeting(opp,data):
        data=data or {}
        vals={
          "university_ids":sorted(set(int(x) for x in data.get("university_ids",[]))),
          "program_ids":sorted(set(int(x) for x in data.get("program_ids",[]))),
          "years":sorted(set(int(x) for x in data.get("years",[]))),
          "semesters":sorted(set(int(x) for x in data.get("semesters",[]))),
        }
        if any(x<=0 for k in ("university_ids","program_ids","years","semesters") for x in vals[k]): raise ValueError("Academic targeting IDs must be positive")
        if any(x not in range(1,7) for x in vals["years"]+vals["semesters"]): raise ValueError("Year and semester must be 1-6")
        for M in (OpportunityUniversityTarget,OpportunityProgramTarget,OpportunityYearTarget,OpportunitySemesterTarget):
            M.query.filter_by(opportunity_id=opp.id).delete(synchronize_session=False)
        for x in vals["university_ids"]: db.session.add(OpportunityUniversityTarget(opportunity_id=opp.id,university_id=x))
        for x in vals["program_ids"]: db.session.add(OpportunityProgramTarget(opportunity_id=opp.id,program_id=x))
        for x in vals["years"]: db.session.add(OpportunityYearTarget(opportunity_id=opp.id,year=x))
        for x in vals["semesters"]: db.session.add(OpportunitySemesterTarget(opportunity_id=opp.id,semester=x))
        return vals

    def visible_query(user):
        q=(Opportunity.query.join(Organisation,Opportunity.organisation_id==Organisation.id)
          .filter(Opportunity.status=="published",Opportunity.expiry_date>datetime.utcnow(),
                  Organisation.verification_status=="verified",Organisation.is_active.is_(True)))
        dims=((OpportunityUniversityTarget,OpportunityUniversityTarget.university_id,user.university_id),
              (OpportunityProgramTarget,OpportunityProgramTarget.program_id,user.program_id),
              (OpportunityYearTarget,OpportunityYearTarget.year,user.year),
              (OpportunitySemesterTarget,OpportunitySemesterTarget.semester,user.semester))
        for M,col,val in dims:
            # Use uncorrelated opportunity-id subqueries rather than relying on
            # SQLAlchemy's implicit correlation rules. Each academic dimension
            # is independent: an opportunity with no targets for that dimension
            # is unrestricted; otherwise the student's current value must be
            # one of that dimension's target values.
            targeted_opportunity_ids = select(M.opportunity_id).distinct()
            q=q.filter(
                or_(
                    ~Opportunity.id.in_(targeted_opportunity_ids),
                    Opportunity.id.in_(
                        select(M.opportunity_id).where(col == val)
                    ) if val is not None else False,
                )
            )
        return q

    def public(opp,uid):
        org=db.session.get(Organisation,opp.organisation_id)
        saved=SavedOpportunity.query.filter_by(user_id=uid,opportunity_id=opp.id).first() is not None
        return {"id":opp.id,"title":opp.title,"description":opp.description,"opportunity_type":opp.opportunity_type,
          "location":opp.location,"is_remote":opp.is_remote,"application_url":opp.application_url,
          "application_instructions":opp.application_instructions,
          "application_deadline":opp.application_deadline.isoformat() if opp.application_deadline else None,
          "expiry_date":opp.expiry_date.isoformat() if opp.expiry_date else None,
          "published_at":opp.published_at.isoformat() if opp.published_at else None,
          "view_count":opp.view_count,"saved":saved,"targeting":targeting(opp),
          "organisation":{"id":org.id,"name":org.name,"logo_url":org.logo_url,"website":org.website} if org else None}

    @app.get("/opportunities")
    def browse_opportunities():
        uid=session.get("user_id")
        if not uid:return jsonify({"error":"Not logged in"}),401
        user=db.session.get(User,uid)
        q=visible_query(user)
        search=(request.args.get("q") or "").strip()
        if search:q=q.filter(Opportunity.title.ilike(f"%{search}%"))
        typ=request.args.get("opportunity_type")
        if typ:
            if typ not in OPPORTUNITY_TYPES:return jsonify({"error":"Invalid opportunity_type"}),400
            q=q.filter(Opportunity.opportunity_type==typ)
        remote=request.args.get("is_remote")
        if remote is not None:q=q.filter(Opportunity.is_remote.is_(remote.lower()=="true"))
        try:page=max(1,int(request.args.get("page",1)))
        except ValueError:page=1
        rows=q.order_by(Opportunity.published_at.desc()).offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE).all()
        return jsonify({"page":page,"opportunities":[public(o,uid) for o in rows]})

    @app.get("/opportunities/<int:opportunity_id>")
    def opportunity_detail(opportunity_id):
        uid=session.get("user_id")
        if not uid:return jsonify({"error":"Not logged in"}),401
        opp=visible_query(db.session.get(User,uid)).filter(Opportunity.id==opportunity_id).first()
        if not opp:return jsonify({"error":"Opportunity not found"}),404
        opp.view_count=(opp.view_count or 0)+1;db.session.commit()
        return jsonify(public(opp,uid))

    @app.post("/opportunities/<int:opportunity_id>/save")
    @require_csrf
    def save_opportunity(opportunity_id):
        uid=session.get("user_id")
        if not uid:return jsonify({"error":"Not logged in"}),401
        if not visible_query(db.session.get(User,uid)).filter(Opportunity.id==opportunity_id).first():return jsonify({"error":"Opportunity not found"}),404
        if not SavedOpportunity.query.filter_by(user_id=uid,opportunity_id=opportunity_id).first():
            try:
                db.session.add(SavedOpportunity(user_id=uid,opportunity_id=opportunity_id))
                db.session.commit()
            except IntegrityError:
                # Another concurrent request may have inserted the same save
                # between our existence check and commit. The unique
                # constraint makes that race safe; treat the winner as success.
                db.session.rollback()
        return jsonify({"message":"Saved"})

    @app.delete("/opportunities/<int:opportunity_id>/save")
    @require_csrf
    def unsave_opportunity(opportunity_id):
        uid=session.get("user_id")
        if not uid:return jsonify({"error":"Not logged in"}),401
        row=SavedOpportunity.query.filter_by(user_id=uid,opportunity_id=opportunity_id).first()
        if row:db.session.delete(row);db.session.commit()
        return jsonify({"message":"Removed"})

    @app.get("/opportunities/saved")
    def saved_opportunities():
        uid=session.get("user_id")
        if not uid:return jsonify({"error":"Not logged in"}),401
        user=db.session.get(User,uid)
        rows=SavedOpportunity.query.filter_by(user_id=uid).order_by(SavedOpportunity.created_at.desc()).all()
        visible={o.id:o for o in visible_query(user).filter(Opportunity.id.in_([r.opportunity_id for r in rows])).all()} if rows else {}
        return jsonify({"saved":[public(visible[r.opportunity_id],uid) for r in rows if r.opportunity_id in visible]})

    @app.patch("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/targeting")
    @require_csrf
    def update_opportunity_targeting(organisation_id,opportunity_id):
        uid=session.get("user_id");opp=db.session.get(Opportunity,opportunity_id)
        if not uid or not opp or opp.organisation_id!=organisation_id:return jsonify({"error":"Opportunity not found"}),404
        member=OrganisationMember.query.filter_by(organisation_id=organisation_id,user_id=uid).first()
        if not member:return jsonify({"error":"Organisation not found"}),404
        if opp.status not in ("draft","rejected"):return jsonify({"error":"Targeting can only be changed while draft or rejected"}),400
        try:out=set_targeting(opp,request.get_json(silent=True) or {})
        except ValueError as e:return jsonify({"error":str(e)}),400
        db.session.commit();return jsonify({"targeting":out})

    @app.get("/opportunities/<int:opportunity_id>/targeting")
    def opportunity_targeting(opportunity_id):
        uid=session.get("user_id");u=db.session.get(User,uid) if uid else None
        if not u or not u.is_admin:return jsonify({"error":"Admin access required"}),403
        opp=db.session.get(Opportunity,opportunity_id)
        if not opp:return jsonify({"error":"Opportunity not found"}),404
        return jsonify(targeting(opp))
    # Remove only stale duplicate public Opportunity rules after the authoritative
    # handlers above have been registered. Doing this before registration leaves
    # Flask with a Rule that points at a deleted endpoint.
    _authoritative_endpoints={"browse_opportunities","opportunity_detail",
                              "save_opportunity","unsave_opportunity",
                              "saved_opportunities"}
    _public_opportunity_rules={"/opportunities",
                               "/opportunities/<int:opportunity_id>",
                               "/opportunities/saved",
                               "/opportunities/<int:opportunity_id>/save"}
    for _rule in list(app.url_map.iter_rules()):
        if (_rule.rule in _public_opportunity_rules
                and _rule.endpoint not in _authoritative_endpoints):
            if _rule in app.url_map._rules:
                app.url_map._rules.remove(_rule)
            _rules_for_endpoint=app.url_map._rules_by_endpoint.get(_rule.endpoint)
            if _rules_for_endpoint and _rule in _rules_for_endpoint:
                _rules_for_endpoint.remove(_rule)
            if not _rules_for_endpoint:
                app.url_map._rules_by_endpoint.pop(_rule.endpoint,None)
                app.view_functions.pop(_rule.endpoint,None)
    app.url_map._remap=True
    app.opportunity_targeting_models=(OpportunityUniversityTarget,OpportunityProgramTarget,OpportunityYearTarget,OpportunitySemesterTarget,SavedOpportunity)
