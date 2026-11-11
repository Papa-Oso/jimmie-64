-- Splits for the run clock: at each star, how far ahead or behind this attempt is.
--
-- Compared against the best finished run's time at that star when there is one; until a run has
-- been finished, against the fastest this save has ever reached that star. Shown silently on the
-- clock; Jimmie never talks about pace (owner's rule).
--
-- Pure logic, no engine calls: the caller passes load(key) -> number or nil and save(key, number).
-- Times in milliseconds.
local M = {}

function M.new(load, save)
    local self = {}
    local function get(key)
        local ok, v = pcall(load, key)
        v = ok and tonumber(v) or nil
        return (v and v > 0) and v or nil
    end
    -- A star was collected at `ms` on this attempt. Returns the difference from the reference
    -- (negative is ahead), or nil when there is nothing to compare with yet.
    function self.star(n, ms)
        if type(n) ~= "number" or type(ms) ~= "number" or n < 1 or n > 16 or ms <= 0 then return nil end
        local reach = get("reach_" .. n)
        local ref = get("pb_" .. n) or reach
        if not reach or ms < reach then pcall(save, "reach_" .. n, ms) end
        return ref and (ms - ref) or nil
    end
    -- A run finished. When it is the new best, its star times become the reference.
    function self.finish(is_best, split_of)
        if not is_best then return end
        for n = 1, 16 do
            local ok, ms = pcall(split_of, n)
            if ok and type(ms) == "number" and ms > 0 then pcall(save, "pb_" .. n, ms) end
        end
    end
    return self
end

-- "-0:02.1" or "+1:14.0"; "" when there is nothing to show.
function M.delta(ms)
    if type(ms) ~= "number" then return "" end
    local sign = ms < 0 and "-" or "+"
    local tenths = math.floor(math.abs(ms) / 100 + 0.5)
    return string.format("%s%d:%02d.%d", sign, math.floor(tenths / 600), math.floor(tenths / 10) % 60, tenths % 10)
end

return M
