# CNC Lathe CL-200 — Operator and Maintenance Manual (sample)

Machine type: cnc_lathe. Units on the floor: L1-LATHE-01, L1-LATHE-02.
This is a fictional sample manual written for the FloorMitra demo.

## 1. Safety before any work
- Press the red EMERGENCY STOP before opening the chuck guard.
- For any work inside the machine (belts, coolant pump, turret), follow SOP-LOTO-01 (lockout/tagout):
  switch off the main isolator, put your own lock and tag, and test that the machine cannot start.
- Never hold a part by hand while the spindle is turning. Wear safety glasses.

## 2. Alarm codes
| Code | Meaning | What the operator does |
|---|---|---|
| E-101 | Spindle overload (motor current too high) | Stop the cycle. Check the depth of cut and the tool tip. Reduce feed by 20%. If it comes back twice in one shift, raise a fault ticket. |
| E-102 | Spindle drive overheating | Let the machine cool 15 minutes with the fan running. Clean the drive cabinet filter (section 4.2). |
| E-205 | Coolant level low | Top up coolant (5% concentrate mix). If the level drops again within a day, check for a leak at the pump seal. |
| E-207 | Coolant pump not running | Lockout first. Check the pump fuse F7. Replace the pump if the motor hums but does not turn (part CP-60). |
| E-310 | Turret not indexing | Check air pressure is at least 5 bar. Clean chips around the turret. If it still fails, maintenance only. |
| E-420 | Chuck pressure low | Do not run. Hydraulic pressure must be 25–30 bar. Check the hydraulic oil level. Maintenance only. |

## 3. Unusual noise or vibration
- A high-pitched whine that rises with spindle speed usually means a worn spindle belt. Belt part: SB-1250.
- Knocking at low speed: check that the workpiece is clamped and the tool holder is tight.
- Vibration marks (chatter) on the part: reduce speed by 10–15%, shorten the tool overhang.
- A worn belt must be replaced by maintenance (about 40 minutes, lockout needed).

## 4. Daily and weekly checks
### 4.1 Daily (operator, 5 minutes)
- Coolant level, hydraulic oil level (sight glass), air pressure 5–6 bar, chip tray emptied.
### 4.2 Weekly (maintenance)
- Clean the drive cabinet air filter (part AF-200 if torn). Check spindle belt tension and wear.
- Grease the tailstock (2 strokes of EP2 grease).

## 5. Spare parts
| Part no. | Name |
|---|---|
| SB-1250 | Spindle drive belt |
| CP-60 | Coolant pump 60 W |
| AF-200 | Drive cabinet air filter |
| CI-12 | Carbide insert (box of 10) |
