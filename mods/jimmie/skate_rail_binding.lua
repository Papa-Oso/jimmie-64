-- Current-frame, exact-owner render binding. Never writes locomotion or animation.
local M={}
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<1e8 end
local function point(p) return type(p)=='table' and finite(p.x) and finite(p.y) and finite(p.z) end
local function same(a,b,epsilon) return finite(a) and finite(b) and math.abs(a-b)<=(epsilon or 0) end
local function samePoint(a,b,epsilon)
 return point(a) and point(b) and same(a.x,b.x,epsilon) and same(a.y,b.y,epsilon) and same(a.z,b.z,epsilon)
end
local function angle(a,b) return finite(a) and finite(b) and a%65536==b%65536 end
local function root(o) return {x=o.oPosX,y=o.oPosY,z=o.oPosZ} end
local function copy(p) return {x=p.x,y=p.y,z=p.z} end
local function native(o) return {yaw=o.oFaceAngleYaw,pitch=o.oFaceAnglePitch,roll=o.oFaceAngleRoll} end
local function sameAngles(a,b)
 return type(a)=='table' and type(b)=='table' and angle(a.yaw,b.yaw) and angle(a.pitch,b.pitch) and angle(a.roll,b.roll)
end
local function actors(c) return {c.body,c.board,c.brace} end
local function owns(o,c) return o~=nil and (o==c.body or o==c.board or o==c.brace) end
local function protected(o,c)
 if type(c.players)~='table' then return true end
 for _,m in pairs(c.players) do
  if m and (o==m.marioObj or o==m.heldObj or o==m.riddenObj) then return true end
 end
 return false
end
function M.new(d)
 assert(d and d.anchor and d.clips and type(d.animationName)=='function' and type(d.setGfxPos)=='function','presentation dependencies required')
 local snapshot=nil
 -- Only objects previously shifted by this binding may need a pause-time reset.
 local shifted=setmetatable({}, {__mode='k'})
 local stats={published=0,rejected=0,rendered=0,reason="empty"}
 local lastRenderByPart={}
 local self={}
 function self:status()
  local records={}
  for role,r in pairs(lastRenderByPart) do
   records[role]={ownerRole=r.ownerRole,source=r.source,frame=r.frame,certificateFrame=r.certificateFrame,
    publicationId=r.publicationId,scene=r.scene,sceneKey=r.sceneKey,physical=copy(r.physical),gfx=copy(r.gfx),delta=copy(r.delta),
    native={yaw=r.native.yaw,pitch=r.native.pitch,roll=r.native.roll},animationName=r.animationName,poseFrame=r.poseFrame,residual=r.residual}
  end
  return {published=stats.published,rejected=stats.rejected,rendered=stats.rendered,reason=stats.reason,
   active=snapshot~=nil,frame=snapshot and snapshot.frame,lastRenderByPart=records}
 end
 local function reject(reason) stats.rejected=stats.rejected+1;stats.reason=reason;return false,reason end
 function self:clear() snapshot=nil;stats.reason="cleared" end
 local function contextValid(c)
  local controller=c.controller
  return c.enabled==true and c.paused~=true and c.dying~=true and c.externalOwner~=true
   and c.body and c.board and c.body~=c.board and c.brace~=c.body and c.brace~=c.board
   and (type(c.scene)=="number" or type(c.scene)=="string") and type(c.sceneKey)=="string" and finite(c.frame) and c.frame==math.floor(c.frame)
   and controller and controller.body==c.body and controller.board==c.board and controller.scene==c.scene
   and not controller.external and not controller.dying and controller.output
   and (controller.output.clip=='balance042' or (JIMMIE_GRIND_CLIPS~=nil and JIMMIE_GRIND_CLIPS[controller.output.clip]==true)) and finite(controller.output.heading)
   and controller.output.heading==math.floor(controller.output.heading)
   and c.motion and c.motion.grind==true and c.motion.raisedPresentation
 end
 local function inspect(o,c,expected,name,frame)
  if not o or o.activeFlags==0 or protected(o,c) then return nil end
  local g=o.header and o.header.gfx
  local a=g and g.animInfo
  if not a or not a.curAnim or g.throwMatrix~=nil or o.oGraphYOffset~=0 then return nil end
  if not samePoint(root(o),expected.root) or not sameAngles(native(o),expected.native) then return nil end
  local scale=g.scale
  if not scale or not same(scale.x,.62,1e-6) or not same(scale.y,.62,1e-6) or not same(math.abs(scale.z),.62,1e-6) then return nil end
  if d.animationName(o)~=name or a.animFrame~=frame or a.animFrameAccelAssist~=frame*65536 or a.animAccel~=65536 then return nil end
  -- Flag 2 prevents the native renderer advancing the controller-selected frame.
  if a.curAnim.flags~=5 then return nil end
  return {object=o,pointer=a.curAnim,name=name,frame=frame,scale={x=scale.x,y=scale.y,z=scale.z}}
 end
 function self:publish(c)
  self:clear()
  if not contextValid(c) then return reject('inactive') end
  local certificate=c.motion.raisedPresentation
  local out=c.controller.output
  local clip=d.clips[out.clip]
  if type(certificate)~='table' or certificate.certificateFrame~=c.frame
   or not point(certificate.physical) or not point(certificate.certifiedDelta)
   or type(certificate.visual)~='table' or not clip
   or not finite(out.frame) or out.frame<0 or out.frame>=clip.frames or out.frame~=math.floor(out.frame) then return reject('certificate') end
  local expected={root=root(c.body),native=native(c.body)}
  if not samePoint(expected.root,certificate.physical) or not sameAngles(expected.native,certificate.native) then return reject('certified-pose') end
  local boardName=out.heading%2==1 and clip.boardReverse or clip.board
  local result=d.anchor.compute({root=expected.root,
   rail={a=certificate.visual.a,b=certificate.visual.b,verified=true},heading=certificate.heading,
   incline=certificate.incline,native=expected.native,clip=boardName,blend=1,safetyMargin=6.66})
  if not result.ok or not samePoint(result.fullDelta,certificate.certifiedDelta,1e-6) then return reject('certified-delta') end
  local entries={}
  for i,o in ipairs(actors(c)) do
   local e=inspect(o,c,expected,i==2 and boardName or clip.body,out.frame)
   if not e then return reject('actor-pose') end
   entries[#entries+1]=e
  end
  snapshot={body=c.body,board=c.board,brace=c.brace,scene=c.scene,sceneKey=c.sceneKey,frame=c.frame,
   motion=c.motion,certificate=certificate,controller=c.controller,output=out,heading=out.heading,poseFrame=out.frame,
   root=expected.root,native=expected.native,entries=entries,residual=result.maxTruckResidual,publicationId=stats.published+1,
   travelHeading=certificate.heading,incline=certificate.incline,
   a={x=certificate.visual.a.x,y=certificate.visual.a.y,z=certificate.visual.a.z},
   b={x=certificate.visual.b.x,y=certificate.visual.b.y,z=certificate.visual.b.z},
   delta={x=result.fullDelta.x,y=result.fullDelta.y,z=result.fullDelta.z}}
  stats.published=stats.published+1;stats.reason="published"
  return true
 end
 local function current(c,s)
  if not contextValid(c) or c.body~=s.body or c.board~=s.board or c.brace~=s.brace
   or c.scene~=s.scene or c.sceneKey~=s.sceneKey or c.frame~=s.frame
   or c.motion~=s.motion or c.motion.raisedPresentation~=s.certificate
   or c.controller~=s.controller or c.controller.output~=s.output
   or c.controller.output.heading~=s.heading or c.controller.output.frame~=s.poseFrame then return false end
  local cert=c.motion.raisedPresentation
  if cert.certificateFrame~=s.frame or not samePoint(cert.physical,s.root)
   or not samePoint(cert.certifiedDelta,s.delta,1e-6) or not sameAngles(cert.native,s.native)
   or cert.heading~=s.travelHeading or cert.incline~=s.incline or type(cert.visual)~="table"
   or not samePoint(cert.visual.a,s.a) or not samePoint(cert.visual.b,s.b) then return false end
  for _,e in ipairs(s.entries) do
   local v=inspect(e.object,c,s,e.name,e.frame)
   if not v or v.pointer~=e.pointer or not samePoint(v.scale,e.scale) then return false end
  end
  return true
 end
 function self:render(o,c)
  if not owns(o,c) or protected(o,c) then return false,'foreign-object' end
  local s=snapshot
  if s and current(c,s) then
   local g=o.header.gfx
   if not g.angle or not sameAngles({pitch=g.angle.x,yaw=g.angle.y,roll=g.angle.z},s.native) then
    self:clear()
   else
    -- Absolute physical root, never the previous gfx value: repeated renders are idempotent.
    d.setGfxPos(o,o.oPosX+s.delta.x,o.oPosY+s.delta.y,o.oPosZ+s.delta.z)
    shifted[o]=true
    stats.rendered=stats.rendered+1;stats.reason="rendered"
    local role=o==c.body and 'body' or (o==c.board and 'board' or 'brace')
    lastRenderByPart[role]={ownerRole=role,source='HOOK_ON_OBJECT_RENDER',frame=c.frame,certificateFrame=s.frame,
     publicationId=s.publicationId,scene=s.scene,sceneKey=s.sceneKey,physical=root(o),gfx=copy(o.header.gfx.pos),delta=copy(s.delta),
     native=native(o),animationName=d.animationName(o),poseFrame=o.header.gfx.animInfo.animFrame,residual=s.residual}
    return true
   end
  else self:clear() end
  -- Do not fight crash/rejoin or another animation owner. Pausing sacrifices the
  -- offset freeze rather than extending a collision certificate beyond its frame.
  if shifted[o] and c.externalOwner~=true and c.dying~=true and o.activeFlags~=0 then
   d.setGfxPos(o,o.oPosX,o.oPosY+(o.oGraphYOffset or 0),o.oPosZ)
   shifted[o]=nil
  end
  stats.reason='invalidated'
  return false,'invalidated'
 end
 return self
end
return M
