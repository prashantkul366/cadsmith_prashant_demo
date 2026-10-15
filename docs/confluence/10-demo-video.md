# 🎬 Demo Video

Sped-up recording of Text to CAD generating a part from a text prompt,
then validating it, editing it and producing its drawing.

> **[Upload the MP4 here]** — `/` → Files & images, or drag it in. If it is
> over the upload ceiling (commonly 100 MB, set by your admin), put it on
> SharePoint or Stream and link it here instead. Do not compress it to the
> point where the dimensions on screen stop being readable — being able to
> read them is the point of the clip.

## What you'll see

1. **Describe** — the part is typed in plain English
2. **Build** — the agents plan the part, write the CAD code and build the
   solid in the kernel
3. **Check** — the kernel measures the part against what the plan claimed,
   and a vision Judge reviews three rendered views
4. **Adjust** — dimensions are changed with sliders and the part rebuilds
   in about a second, with no model call
5. **Hand off** — the A3 drawing and the exports are produced

## Worth pointing out when you show it

- Nothing in the clip is a mock-up. The mesh is the STL the kernel
  exported, the numbers are the kernel's own measurements, and the code is
  what the Coder actually wrote.
- The clip is sped up. Real time for an agent-built part was about two
  minutes against a small local model; a catalogue part is about two
  seconds.
- Chapter timestamps are deliberately not listed here, because the ones
  from the original recording do not match the sped-up cut. If chapters
  are wanted, take the times off the final file.
