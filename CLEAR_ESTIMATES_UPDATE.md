# BEAST v2.8 — a simpler estimate screen

App: `fieldwork-2.8-clear-estimates`  
Image renderer: `dots-aa-v1`  
Adviser prompt: unchanged, `adaptive-reaction-v7-repair`

## Response screens

The first estimate appears once, in a grey square. The line starts blank; the
participant clicks, drags or types to choose a value before continuing.

The final response uses one number line with three distinct roles:

- **Previous estimate:** grey square and grey label, “YOUR PREVIOUS ESTIMATE: …”.
- **AI advice:** cyan pointer directed at the line. The label, advice number and
  verbal note share one cyan text block, wrapping naturally on narrow screens.
- **Final estimate:** red square containing the current value, a red heading
  “Enter your final estimate”, and a matching Confirm button.

The labels use separate rows and are kept within the available line width.
The markers occupy separate vertical positions connected to the same numerical
axis. This makes equal and nearby values distinguishable. Squares and the triangle
remain in front of the rail; no source relies on colour alone.

Removed: the separate You/AI number cards, the legend, duplicate first-estimate
readout, intermediate numerical scale labels, final-screen helper text and visible
trial/round counters during decisions. The scale keeps only its 1 and 400 endpoints.
A quiet progress bar remains. Round information is available to screen readers and
at breaks. Researcher diagnostics remain available below the task.

The task has a dark background with larger type. The source-label colours against
the background have calculated contrast ratios of approximately 10.3:1 (grey),
11.4:1 (cyan), and 6.7:1 (red). This is a colour-contrast check, not a complete
accessibility certification. Researcher and information pages retain their light theme.

In actual pilots, the final choice still starts at the participant's initial
estimate. Numerical advice, condition schedules, model inputs, ratings, timing
instrumentation, private access gates and the v2.7 retry policy are retained.
Changing colour and layout can affect attention: comparisons should use the same
interface version across conditions.

## Smoother dot images

The original placement algorithm, seeds, dot counts, logical canvas size and
nominal radius are retained. The pilot now draws at 2048 × 2048 pixels and downsamples
with antialiasing to 1024 × 1024. Images are displayed at the existing maximum
512 × 512 CSS-pixel size, providing extra resolution for sharper displays.
Black dots and the white field are retained; no per-dot gradients or reflections
are added. The image panel has a restrained shadow and rounded outer corners.

Smoothing changes the raster's edge coverage, so the new images are not pixel-identical
to the simulation's legacy arrays. The default standalone generator still produces
the legacy raster; `python stimuli.py --smooth` produces the new renderer.

The server generates smooth PNGs in a versioned directory on startup, even when old
images already exist. It does not overwrite those old files. Stimulus URLs remain
protected, and the served download filename does not reveal the dot count. PNGs
are not included in this update archive or published with it.

`ui_version` and `stimulus_render_version` are recorded in trial diagnostics,
session configuration and export metadata. Model-comparison rows separate the
versions. The broad condition timing table can still pool versions; filter the
diagnostic export when comparing older and newer pilots.

## Preview and install

Open `validation/estimate-preview.html` locally in your browser. It contains the
actual estimate UI code and styles, uses synthetic values, makes no API requests
and saves no responses. Buttons switch between the first estimate, final estimate,
and equal-value example. The final example starts at 119 to illustrate the reported
151 / 160 / 119 case; this demonstration does not change the actual pilot's starting
value. Resize the browser to assess the layout on smaller screens.

The preview can be rebuilt with `python build_estimate_preview.py`.

1. Export any pilot data you need to retain and update between sessions.
2. Unzip the update and upload its contents into the existing GitHub repository
   root, replacing matching files and preserving folders. Include the new
   `static/estimate.js`, updated templates, `assets.py` and `stimuli.py`.
3. Allow Render's existing automatic deployment to complete. No environment/key
   changes are required for this interface update.
4. Start a new pilot and confirm `fieldwork-2.8-clear-estimates` in the workspace.
   Check the first/final estimates, nearby and equal markers, dragging, typing and
   mobile layout before gathering further pilot feedback.

This ZIP updates the existing repository; it is not a standalone full application.
GitHub write access was previously rejected by the integration, so it is supplied
for the existing manual-upload workflow. It is not a claim that v2.8 is deployed.

## Validation

- **192 Python tests passed**, covering existing experimental behavior and new
  raster, count, private-delivery and version/export checks.
- **8 DOM interaction tests passed**, covering a blank first answer, keyboard and
  pointer responses, range endpoints, nearby/equal markers, native range events,
  safe advice rendering and clearing a typed initial answer.
- Three legacy image hashes match the pre-update generator. Smooth images retain
  the same dot centres; a dense test image has exactly 256 connected dots.
- JavaScript/Python syntax, Jinja template compilation, and the consent,
  instructions, task and researcher routes were checked.
- The generated smooth practice image was visually inspected. The standalone
  preview uses the same JavaScript and CSS as the task.

Run `python smoke_test.py` for Python checks. Run `npm install` followed by
`npm run test:ui` for DOM checks. The existing `npm run test:browser` test was updated
for the new interface, but was **not run here** because the preview browser was
previously blocked. No claim of full browser, Safari, mobile visual validation or
live-model evaluation is made. The offline preview is provided for that visual review.
