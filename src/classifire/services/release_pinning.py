from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Estimate, LibraryRelease
from .release_scope import validate_runtime_scope
PIN_FIELDS={'pricing':'pricing_release_id','technical':'technical_release_id','rules':'rules_release_id','products':'products_release_id','labour':'labour_release_id','markups':'markups_release_id'}
OPTIONAL={'formulas':'formula_release_id','brand':'brand_release_id'}
def active_release(db:Session, kind:str):
    return db.scalar(select(LibraryRelease).where(LibraryRelease.library_type==kind,LibraryRelease.status=='active').order_by(LibraryRelease.created_at.desc()))
def pin_current_releases(db:Session, estimate:Estimate):
    if estimate.locked_at or estimate.snapshot_hash or estimate.status not in {'draft','in_review'}: raise ValueError('Release basis can only be refreshed while estimate is editable')
    basis={k:active_release(db,k) for k in PIN_FIELDS}; missing=[k for k,v in basis.items() if v is None]
    if missing: raise ValueError('Missing active releases: '+', '.join(sorted(missing)))
    result={}; pinned=datetime.now(timezone.utc).isoformat()
    for k,f in PIN_FIELDS.items():
        r=basis[k]; setattr(estimate,f,r.id); result[k]={'release_id':r.id,'version':r.version,'hash':r.release_hash,'effective_date':r.effective_date.isoformat() if r.effective_date else None,'status':r.status,'pinned_at':pinned}
    return result
def release_basis_for_estimate(db:Session, estimate:Estimate):
    out={}
    for k,f in {**PIN_FIELDS,**OPTIONAL}.items():
        rid=getattr(estimate,f,None); r=db.get(LibraryRelease,rid) if rid else None
        out[k]=None if not rid else {'release_id':rid,'version':r.version if r else 'Missing release record','hash':r.release_hash if r else None,'effective_date':r.effective_date if r else None,'status':r.status if r else 'missing'}
    return out
def validate_estimate_release_basis(db:Session, estimate:Estimate):
    errors=[]
    for k,f in PIN_FIELDS.items():
        rid=getattr(estimate,f,None)
        if not rid: errors.append(f'{k}: no release pinned'); continue
        r=db.get(LibraryRelease,rid)
        if not r: errors.append(f'{k}: pinned release missing')
        elif not r.release_hash: errors.append(f'{k}: pinned release has no hash')
    errors.extend(validate_runtime_scope(db, estimate))
    return list(dict.fromkeys(errors))
