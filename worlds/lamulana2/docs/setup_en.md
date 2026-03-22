Alpha release of the La-Mulana 2 APWorld.

This port features most functionalities of (and depends on) the original randomizer by Coookie93. 
(https://github.com/Coookie93/LaMulana2Randomizer)

Due to the addition of AP items and different item distribution (forward fill instead of assumed fill), several options may lead to unbeatable seeds. This is still a work in progress but it's stable enough to produce beatable runs and calls FillError whenever the final boss cannot be reached. Currently the highest rate of seeds failing is when Randomized Dissonance is off with a non Village of Departure start, or when using full entrance randomization with starts in Hall of Malice and Ancient Chaos, or just due to orphaned islands with bosses in general.

**_Please set up the LaMulana2Archipelago BepInEx Mod prior to setting up the APWorld._**
https://github.com/Crownmuri/LaMulana2Archipelago

# How to Play 
1. Download the APWorld and install it (putting it into the `archipelago/custom_worlds` folder)
2. Download and LM2 YAML template and put it into the `archipelago/Players folder` after adjusting your name and preferred settings
3. Generate the seed and hope it doesn't result in a FillError 
4. The output will contain an `AP_[#####]_P[#]_[PlayerName].zip` container with your `seed.lm2r`
5. Put the `seed.lm2r` file in the original LaMulana2Randomizer's seed folder:
`..\Steam\steamapps\common\La-Mulana 2\LaMulana2Randomizer\Seed`
6. Launch the game.
7. LaMulana2Archipelago will automatically attempt to connect to `localhost:38281` with slotname `Lumisa` first, if that fails, you can manually fill in the server, name and password in the GUI in the main menu.
8. Once you're connected you're good to go!

# Ported Features
Same seed writing structure as the original randomizer. This means that the most options are ported:
- Starting Items (Holy Grail, FDC, Hand Scanner, Shell Horn, Codices, Ring, Maps/Software (available at start is untested)
- Randomized Mantras / Shops / Research / Dissonance (switching to Guardians) / Cursed Chests
- Option to remove Maps / Research / excess Skulls (replaced by filler)
- Randomized Starting Weapon / Starting Area
- Logic appends: FDC required / HoM Life Sigil required / DLC item usage / Costume Clip (untested)
- Hard Logic (untested) / Echidna Type (untested)
- Quality of Life features (auto-scan / auto-skulls / starting money & weights / chest colors)
- Entrance Randomization (horizontal / vertical / gates / soul gates / randomized souls / mixed transitions) [may lead to unbeatable seed generation FillError especially when accessibility is set to 'items']

# New Features
- Guardian Specific Ankh Jewels 
This will append Ankh Jewels with boss names at the boss locations in the World.json logic mapping. (e.g. "Ankh Jewel (Fafnir)")
The LM2 Bepinex Mod will live patch the usability of Ankh Jewels for specific bosses.
- Death Link
This will trigger an instant death similar to casting all mantras without meeting all conditions.
The LM2 Bepinex Mod will separately have a toggle button to turn on/off Death Link in the main menu.
- AP Chest Color
You can now choose colors separately for LM2 non-filler chests, LM2 filler chests, and AP item chests.
The LM2 Bepinex Mod will live patch the AP item chest color based on the seed loaded in the server.

# Adjustments
- New filler items
While the seed writer still uses ChestWeight/FakeItem/NPCMoney/FakeScan for placing in-game filler, the filler needed to be able to be sent to the LM2 player from AP at any given time, non-location specific. As a result, the contents of the filler is automatically converted to one of the items below. Currently I have set these filler items to accommodate more purchasing power for AP items in shops.
*1 Coin
*10 Coins
*30 Coins
*50 Coins
*80 Coins
*100 Coins
*1 Weight
*5 Weights
*10 Weights
*20 Weights

- Shop prices
The dynamic sphere based shop price balancing is mostly maintained but I reduced the multiplier by half.
In addition, filler items in shops are free one time purchases instead of converted to [Weights]. 
Balancing might still be required.

# Issues
- Entrance Randomizer FillError (unbeatable seeds -- Ninth Child unreachable due to impossible world built)
- Some untested options (I ported the functions but did not test yet)
- Death Link sometimes not sending out to other players (on AP BepInEx mod side)
- Debug log spam