-- Authored balance stances; the numbers in the names are legacy identifiers only.
local M={seconds={balance038=.3,balance039=.3,balance042=1/3}}
local skins={jimmie3rg='rg',jimmie3='vest',jimmie3nv='tee'}
function M.load(prefix,getId,errorId)
 local skin=skins[prefix];local clips={}
 if not skin or type(getId)~='function' then return clips end
 for _,source in ipairs({'038','039','042'}) do
  local ids={};local complete=true
  for frame=0,11 do
   local ok,id=pcall(getId,string.format('bankaudition_%s_candidate_%s_%02d_geo',skin,source,frame))
   if not ok or type(id)~='number' or id~=id or id<=0 or id==errorId or id%1~=0 then complete=false;break end
   ids[#ids+1]=id
  end
  if complete then clips['balance'..source]=ids end
 end
 return clips
end
return M
