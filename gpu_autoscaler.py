"""Safe, measured Kokoro GPU autoscaling control plane."""
import json, math, os, secrets
from datetime import datetime
import requests
from sqlalchemy import text

BASE = os.environ.get("VAST_API_BASE_URL", "https://console.vast.ai/api/v0").rstrip("/")
KEY = os.environ.get("VAST_API_KEY", "").strip()
GPU = os.environ.get("VAST_GPU_NAME", "RTX_A2000").strip()
GPUS = [x.strip() for x in os.environ.get("VAST_GPU_CANDIDATES", GPU).split(",") if x.strip()]
MAX_DPH = float(os.environ.get("VAST_MAX_DPH_USD", "0.10"))
MAX_SPEND = float(os.environ.get("VAST_MAX_GPU_HOURLY_SPEND_USD", "0.10"))
CREDIT_RESERVE = max(0.0, float(os.environ.get("VAST_MIN_PROVIDER_CREDIT_RESERVE_USD", "5.00")))
MIN_REL = float(os.environ.get("VAST_MIN_RELIABILITY", "0.90"))
DISK_GB = int(os.environ.get("VAST_DISK_GB", "12"))
IDLE_SECONDS = max(60, int(os.environ.get("VAST_IDLE_SECONDS", "300")))
IMAGE = os.environ.get("VAST_WORKER_IMAGE", "ghcr.io/apexstudying-cmd/prepza-kokoro-worker:main").strip()
MODE = os.environ.get("KOKORO_SCALING_MODE", "manual").strip().lower()
DRY_RUN = os.environ.get("KOKORO_AUTOSCALER_DRY_RUN", "true").strip().lower() not in {"0","false","no"}
MAX_WORKERS = max(1, int(os.environ.get("KOKORO_MAX_GPU_WORKERS", "1")))
MAX_PENDING_PER_WORKER = max(1, int(os.environ.get("KOKORO_MAX_PENDING_JOBS_PER_WORKER", "3")))
MAX_PENDING_AGE = max(30, int(os.environ.get("KOKORO_MAX_PENDING_AGE_SECONDS", "120")))
VRAM_SAFETY = min(.95, max(.50, float(os.environ.get("KOKORO_VRAM_SAFETY_FRACTION", ".85"))))
WORKER_VRAM_GB = max(.5, float(os.environ.get("KOKORO_REQUIRED_VRAM_GB", "6.0")))
WORKER_RAM_GB = max(1.0, float(os.environ.get("KOKORO_REQUIRED_HOST_RAM_GB", "12.0")))
STALE_HEARTBEAT = max(90, int(os.environ.get("KOKORO_STALE_HEARTBEAT_SECONDS", "180")))

def db():
    from app import db as _db
    return _db

def now():
    return datetime.utcnow()

def table_ready():
    try:
        db().session.execute(text("SELECT 1 FROM kokoro_gpu_workers LIMIT 1"))
        return True
    except Exception:
        db().session.rollback()
        return False

def headers():
    if not KEY:
        raise RuntimeError("VAST_API_KEY is not configured")
    return {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

def req(method, path, **kwargs):
    r = requests.request(method, BASE + path, headers=headers(), timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()

def _gb(value, assume_mb=False):
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if assume_mb or v > 100:
        v /= 1024.0
    return v

def offer_resources(o):
    vram = _gb(o.get("gpu_ram") or o.get("gpu_ram_gb") or o.get("gpu_ram_mb"), assume_mb=bool(o.get("gpu_ram_mb")))
    ram = _gb(o.get("cpu_ram") or o.get("ram") or o.get("ram_gb") or o.get("host_ram_gb"), assume_mb=False)
    return vram, ram

def capacity(vram_gb, host_ram_gb=None):
    # One Kokoro process/model copy per GPU instance is intentional. VRAM/RAM
    # decide whether the instance is eligible; they do not permit multiple
    # concurrent inference processes on one GPU.
    if _gb(vram_gb) < WORKER_VRAM_GB:
        return 0
    if host_ram_gb is not None and _gb(host_ram_gb) < WORKER_RAM_GB:
        return 0
    return 1

def queue_metrics():
    from app import AiJob
    pending = AiJob.query.filter_by(feature="podcast_audio", status="pending").order_by(AiJob.created_at.asc()).all()
    processing = AiJob.query.filter_by(feature="podcast_audio", status="processing").count()
    age = None
    if pending and pending[0].created_at:
        age = max(0, int((now() - pending[0].created_at).total_seconds()))
    audio = 0.0
    for job in pending:
        try:
            audio += float((job.generation_parameters or {}).get("target_duration_seconds") or 0)
        except (TypeError, ValueError):
            pass
    return {"pending_jobs":len(pending),"processing_jobs":int(processing),
            "queue_depth":len(pending)+int(processing),
            "oldest_pending_age_seconds":age,"queued_audio_seconds":round(audio,2)}

def workers():
    if not table_ready(): return []
    return [dict(x) for x in db().session.execute(text("""
        SELECT id,instance_id,worker_id,offer_id,gpu_name,gpu_vram_gb,host_ram_gb,
               required_vram_gb,required_host_ram_gb,status,worker_index,
               worker_capacity,price_usd_per_hour,created_at,last_job_at,
               last_idle_at,last_heartbeat_at,vram_used_gb,vram_total_gb,last_error,metadata
        FROM kokoro_gpu_workers WHERE status <> 'destroyed' ORDER BY worker_index,id
    """)).mappings().all()]

def upsert_worker(instance_id, offer_id, gpu_name, vram, host_ram, price, status="starting", index=1, metadata=None, worker_id=None):
    params={"instance_id":int(instance_id),"worker_id":worker_id,"offer_id":int(offer_id) if offer_id else None,
            "gpu_name":gpu_name,"vram":vram,"host_ram":host_ram,"status":status,"index":index,
            "capacity":capacity(vram, host_ram),"required_vram":WORKER_VRAM_GB,"required_ram":WORKER_RAM_GB,"price":price,"metadata":json.dumps(metadata or {})}
    db().session.execute(text("""
        INSERT INTO kokoro_gpu_workers
        (instance_id,worker_id,offer_id,gpu_name,gpu_vram_gb,host_ram_gb,required_vram_gb,required_host_ram_gb,status,worker_index,worker_capacity,price_usd_per_hour,metadata)
        VALUES (:instance_id,:worker_id,:offer_id,:gpu_name,:vram,:host_ram,:required_vram,:required_ram,:status,:index,:capacity,:price,CAST(:metadata AS jsonb))
        ON CONFLICT (instance_id) DO UPDATE SET
        worker_id=COALESCE(EXCLUDED.worker_id,kokoro_gpu_workers.worker_id),offer_id=EXCLUDED.offer_id,gpu_name=EXCLUDED.gpu_name,gpu_vram_gb=EXCLUDED.gpu_vram_gb,
        host_ram_gb=EXCLUDED.host_ram_gb,required_vram_gb=EXCLUDED.required_vram_gb,required_host_ram_gb=EXCLUDED.required_host_ram_gb,
        status=EXCLUDED.status,worker_index=EXCLUDED.worker_index,worker_capacity=EXCLUDED.worker_capacity,
        price_usd_per_hour=EXCLUDED.price_usd_per_hour,metadata=EXCLUDED.metadata
    """), params)
    db().session.commit()

def offer(gpu):
    q={"gpu_name":{"eq":gpu},"num_gpus":{"eq":1},"gpu_frac":{"eq":1.0},
       "rentable":{"eq":True},"rented":{"eq":False},"dph_total":{"lte":MAX_DPH},
       "reliability":{"gte":MIN_REL},"type":"on-demand","order":[["dph_total","asc"]],"limit":20}
    data=req("GET","/bundles/",params={"q":json.dumps(q)})
    items=[]
    for x in data.get("offers",[]):
        if str(x.get("gpu_name","")).upper()!=gpu.upper():
            continue
        if int(x.get("num_gpus",1) or 1)!=1 or float(x.get("dph_total",999))>MAX_DPH:
            continue
        vram, ram = offer_resources(x)
        if vram < WORKER_VRAM_GB or ram < WORKER_RAM_GB:
            continue
        items.append(x)
    return sorted(items,key=lambda x:float(x.get("dph_total",999)))[0] if items else None

def best_offer():
    choices=[]
    for gpu in GPUS:
        try:
            o=offer(gpu)
            if not o: continue
            vram, ram = offer_resources(o)
            price=float(o.get("dph_total") or 999)
            choices.append((price,1,gpu,o,vram,ram))
        except Exception:
            continue
    if not choices: return None
    choices.sort(key=lambda x:(x[0], -x[4]))
    return choices[0]

def instance_status(instance_id):
    data=req("GET","/instances/" + str(int(instance_id)) + "/")
    inner=data.get("instances")
    if isinstance(inner,list) and inner: return inner[0]
    if isinstance(inner,dict): return inner
    return data

def provider_credit():
    try:
        data=req("GET","/users/current/")
    except Exception:
        return None
    candidates=("credit","credit_usd","balance","balance_usd","credit_balance")
    for key in candidates:
        value=data.get(key)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass
    return None

def create_instance(o, worker_id):
    required=["PREPZA_INTERNAL_BASE_URL","KOKORO_WORKER_TOKEN","R2_ENDPOINT_URL",
              "R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET"]
    missing=[x for x in required if not os.environ.get(x)]
    if missing: raise RuntimeError("Missing GPU worker environment: " + ", ".join(missing))
    env={x:os.environ[x] for x in required}
    result=req("PUT","/asks/" + str(int(o["id"])) + "/",json={
        "client_id":"me","image":IMAGE,"disk":DISK_GB,
        "label":os.environ.get("VAST_INSTANCE_LABEL","prepza-kokoro-a2000"),
        "runtype":"args","args":[],"env":{**env,"KOKORO_WORKER_ID":worker_id},"force":False})
    if not result.get("success") or not result.get("new_contract"):
        raise RuntimeError("Vast instance creation failed: " + str(result))
    return int(result["new_contract"]),result

def decision(metrics,current,desired,target,action,code,reason,price=None,gpu=None,vram=None,extra=None,host_ram=None,credit=None,projected=None):
    if not table_ready(): return
    db().session.execute(text("""
        INSERT INTO kokoro_gpu_scaling_decisions
        (action,reason_code,reason_text,dry_run,pending_jobs,processing_jobs,queue_depth,
         oldest_pending_age_seconds,queued_audio_seconds,current_workers,desired_workers,target_workers,
         max_workers,max_pending_jobs_per_worker,max_pending_age_seconds,max_gpu_price_usd_per_hour,
         max_gpu_hourly_spend_usd,estimated_incremental_hourly_usd,gpu_name,gpu_vram_gb,vram_used_gb,
         provider_credit_usd,provider_credit_reserve_usd,host_ram_gb,required_vram_gb,required_host_ram_gb,
         projected_hourly_spend_usd,decision_context,metadata)
        VALUES (:action,:code,:reason,:dry,:pending,:processing,:depth,:age,:audio,:current,:desired,:target,
         :max_workers,:max_pending,:max_age,:max_dph,:max_spend,:price,:gpu,:vram,NULL,
         :credit,:reserve,:ram,:required_vram,:required_ram,:projected,CAST(:context AS jsonb),CAST(:metadata AS jsonb))
    """),{"action":action,"code":code,"reason":reason,"dry":DRY_RUN,"pending":metrics["pending_jobs"],
       "processing":metrics["processing_jobs"],"depth":metrics["queue_depth"],"age":metrics["oldest_pending_age_seconds"],
       "audio":metrics["queued_audio_seconds"],"current":current,"desired":desired,"target":target,
       "max_workers":MAX_WORKERS,"max_pending":MAX_PENDING_PER_WORKER,"max_age":MAX_PENDING_AGE,
       "max_dph":MAX_DPH,"max_spend":MAX_SPEND,"price":price,"gpu":gpu,"vram":vram,
       "credit":credit,"reserve":CREDIT_RESERVE,"ram":host_ram,"required_vram":WORKER_VRAM_GB,
       "required_ram":WORKER_RAM_GB,"projected":projected,
       "context":json.dumps({
           "hard_limits":{"max_workers":MAX_WORKERS,"max_gpu_price_usd_per_hour":MAX_DPH,
                          "max_gpu_hourly_spend_usd":MAX_SPEND,"provider_credit_reserve_usd":CREDIT_RESERVE},
           "resource_requirements":{"required_vram_gb":WORKER_VRAM_GB,"required_host_ram_gb":WORKER_RAM_GB},
           "queue":metrics,
           "extra":extra or {},
       }),"metadata":json.dumps(extra or {})})
    db().session.commit()

def target_for(metrics,current,per_gpu_capacity=1):
    if metrics["queue_depth"] <= 0:
        return 0
    # One process/model per GPU instance. Pending jobs therefore map to
    # independent GPU workers, never to extra processes on one GPU.
    target=max(1,math.ceil(metrics["queue_depth"]/MAX_PENDING_PER_WORKER))
    if metrics["oldest_pending_age_seconds"] is not None and metrics["oldest_pending_age_seconds"]>=MAX_PENDING_AGE:
        target=max(target,current+1)
    return min(MAX_WORKERS,target)

def reconcile():
    metrics=queue_metrics()
    active=workers()
    current=len(active)
    per_gpu=1
    desired=target_for(metrics,current,per_gpu)
    if not KEY:
        decision(metrics,current,desired,current,"blocked","provider_not_configured","Autoscaling blocked because VAST_API_KEY is not configured.")
        return snapshot()
    locked=db().session.execute(text("SELECT pg_try_advisory_lock(hashtext('prepza:kokoro:autoscaler'))")).scalar()
    if not locked: return snapshot("Another autoscaler reconciliation is already running.")
    try:
        recovery = recover_stale_workers()
        active=workers(); current=len(active)
        per_gpu=1
        desired=target_for(metrics,current,per_gpu)
        if desired>current:
            b=best_offer()
            if not b:
                decision(metrics,current,desired,current,"blocked","no_safe_offer","No allowed GPU offer met the configured GPU, price, reliability and on-demand filters.")
                return snapshot()
            price,cap,gpu,o,vram,ram=b
            projected=sum(float(x.get("price_usd_per_hour") or 0) for x in active)+price
            credit=provider_credit()
            if current >= MAX_WORKERS:
                decision(metrics,current,desired,current,"blocked","worker_ceiling",
                         "Scale-up blocked: worker ceiling is " + str(MAX_WORKERS) + ".",price,gpu,vram,
                         host_ram=ram,credit=credit,projected=projected)
                return snapshot()
            if projected>MAX_SPEND:
                decision(metrics,current,desired,current,"blocked","hourly_spend_ceiling",
                         "Scale-up blocked: projected hourly GPU spend " + str(round(projected,4)) +
                         " exceeds hard ceiling " + str(round(MAX_SPEND,4)) + ".",price,gpu,vram,
                         host_ram=ram,credit=credit,projected=projected)
                return snapshot()
            if credit is not None and credit - projected < CREDIT_RESERVE:
                decision(metrics,current,desired,current,"blocked","provider_credit_reserve",
                         "Scale-up blocked: provider credit would fall below the configured reserve of $" +
                         str(round(CREDIT_RESERVE,2)) + ".",price,gpu,vram,
                         host_ram=ram,credit=credit,projected=projected)
                return snapshot()
            reason=("Queue pressure: " + str(metrics["queue_depth"]) + " active/queued jobs; " +
                    str(metrics["pending_jobs"]) + " pending; oldest pending " +
                    str(metrics["oldest_pending_age_seconds"]) + "s.")
            if DRY_RUN or MODE!="automatic":
                decision(metrics,current,desired,current+1,"scale_up_planned","queue_pressure",reason,price,gpu,vram,
                         host_ram=ram,credit=credit,projected=projected)
                return snapshot()
            worker_id=secrets.token_hex(16)
            iid,result=create_instance(o,worker_id)
            upsert_worker(iid,o.get("id"),gpu,vram,ram,price,"starting",current+1,
                           {"create_result":result,"offer":o,"required_vram_gb":WORKER_VRAM_GB,
                            "required_host_ram_gb":WORKER_RAM_GB},worker_id=worker_id)
            decision(metrics,current,desired,current+1,"scale_up","queue_pressure",reason,price,gpu,vram,
                     host_ram=ram,credit=credit,projected=projected)
            return snapshot()
        if desired<current and metrics["queue_depth"]==0:
            candidates=sorted(active,key=lambda x:str(x.get("last_job_at") or ""))
            if candidates:
                victim=candidates[-1]
                last=victim.get("last_job_at")
                idle=int((now()-last).total_seconds()) if last else IDLE_SECONDS
                if idle>=IDLE_SECONDS:
                    reason="Queue is empty and worker " + str(victim["instance_id"]) + " has been idle for " + str(idle) + "s."
                    if DRY_RUN or MODE!="automatic":
                        decision(metrics,current,desired,current-1,"scale_down_planned","idle_timeout",reason,
                                 float(victim.get("price_usd_per_hour") or 0),victim.get("gpu_name"),victim.get("gpu_vram_gb"))
                        return snapshot()
                    req("DELETE","/instances/" + str(int(victim["instance_id"])) + "/")
                    db().session.execute(text("UPDATE kokoro_gpu_workers SET status='destroyed',last_idle_at=:now WHERE instance_id=:id"),
                                         {"now":now(),"id":int(victim["instance_id"])})
                    db().session.commit()
                    decision(metrics,current,desired,current-1,"scale_down","idle_timeout",reason,
                             float(victim.get("price_usd_per_hour") or 0),victim.get("gpu_name"),victim.get("gpu_vram_gb"))
                    return snapshot()
        decision(metrics,current,desired,current,"hold","within_policy",
                 "No scaling action: current capacity is within the configured queue, age, VRAM and spending policy.")
        return snapshot()
    except Exception as exc:
        db().session.rollback()
        decision(metrics,current,desired,current,"error","reconcile_error","Autoscaler error: " + str(exc)[:900])
        return snapshot(str(exc)[:500])
    finally:
        try:
            db().session.execute(text("SELECT pg_advisory_unlock(hashtext('prepza:kokoro:autoscaler'))"))
            db().session.commit()
        except Exception:
            db().session.rollback()

def heartbeat(worker_id,vram_used_gb=None,vram_total_gb=None,status="running"):
    if not table_ready(): return {"ok":False,"reason":"migration_not_applied"}
    db().session.execute(text("""
        UPDATE kokoro_gpu_workers SET status=:status,last_heartbeat_at=:now,
        vram_used_gb=:used,vram_total_gb=:total,worker_capacity=:capacity
        WHERE worker_id=:id
    """),{"status":status,"now":now(),"used":vram_used_gb,"total":vram_total_gb,
          "capacity":capacity(vram_total_gb),"id":worker_id})
    db().session.commit()
    return {"ok":True}

def mark_job_activity():
    if table_ready():
        db().session.execute(text("UPDATE kokoro_gpu_workers SET last_job_at=:now,last_heartbeat_at=:now WHERE status IN ('starting','running')"),{"now":now()})
        db().session.commit()

def recover_stale_workers():
    if not KEY or not table_ready(): return {"recovered":0}
    cutoff=now().timestamp()-STALE_HEARTBEAT
    stale=db().session.execute(text("""
        SELECT instance_id FROM kokoro_gpu_workers
        WHERE status IN ('starting','running') AND last_heartbeat_at IS NOT NULL
        AND EXTRACT(EPOCH FROM last_heartbeat_at)<:cutoff
    """),{"cutoff":cutoff}).mappings().all()
    recovered=0
    for x in stale:
        try:
            s=instance_status(x["instance_id"])
            actual=str(s.get("actual_status") or s.get("status") or "").lower()
            if actual not in {"running","loading","created","starting"}:
                db().session.execute(text("UPDATE kokoro_gpu_workers SET status='error',last_error=:e WHERE instance_id=:id"),
                                     {"e":"Provider reports unavailable: "+actual,"id":int(x["instance_id"])})
                recovered+=1
        except Exception as exc:
            db().session.execute(text("UPDATE kokoro_gpu_workers SET status='error',last_error=:e WHERE instance_id=:id"),
                                 {"e":str(exc)[:1000],"id":int(x["instance_id"])})
            recovered+=1
    db().session.commit()
    return {"recovered":recovered}

def snapshot(extra_reason=None):
    m=queue_metrics(); ws=workers()
    latest=None
    recent=[]
    if table_ready():
        rows=db().session.execute(text("""
            SELECT action,reason_code,reason_text,dry_run,pending_jobs,processing_jobs,queue_depth,
                   current_workers,desired_workers,target_workers,max_workers,max_gpu_price_usd_per_hour,
                   max_gpu_hourly_spend_usd,estimated_incremental_hourly_usd,provider_credit_usd,
                   provider_credit_reserve_usd,gpu_name,gpu_vram_gb,host_ram_gb,required_vram_gb,
                   required_host_ram_gb,projected_hourly_spend_usd,decision_context,created_at
            FROM kokoro_gpu_scaling_decisions
            ORDER BY created_at DESC LIMIT 20
        """)).mappings().all()
        recent=[dict(r) for r in rows]
        latest=recent[0] if recent else None
    return {**m,"workers":ws,"current_workers":len(ws),"max_workers":MAX_WORKERS,
            "max_pending_jobs_per_worker":MAX_PENDING_PER_WORKER,
            "max_pending_age_seconds":MAX_PENDING_AGE,"vram_safety_fraction":VRAM_SAFETY,
            "worker_vram_estimate_gb":WORKER_VRAM_GB,"max_gpu_price_usd_per_hour":MAX_DPH,
            "max_gpu_hourly_spend_usd":MAX_SPEND,"scaling_mode":MODE,"dry_run":DRY_RUN,
            "provider_configured":bool(KEY),"latest_decision":latest,"recent_decisions":recent,"extra_reason":extra_reason,
            "required_vram_gb":WORKER_VRAM_GB,"required_host_ram_gb":WORKER_RAM_GB,
        "provider_credit_reserve_usd":CREDIT_RESERVE,
        "policy":"Queue pressure selects the number of independent GPU workers. Each worker is one process/model copy. VRAM and host RAM are eligibility gates; hard worker, per-GPU price, hourly spend, and provider-credit reserve ceilings always win over available credit."}

def admin_snapshot():
    s=snapshot()
    if KEY:
        try: s["provider"]=req("GET","/users/current/")
        except Exception as exc: s["provider_error"]=str(exc)[:500]
    return s

# Backward-compatible entry points used by the existing podcast queue.
ensure_worker_capacity=reconcile
destroy_if_idle=lambda: reconcile()
scaling_snapshot=snapshot
