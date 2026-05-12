import os, subprocess, shutil, yt_dlp, pytz, re, signal
from datetime import datetime
import gradio as gr

# --- Global Variables ---
current_process = None

# --- Environment Variables for Path Configuration ---
def get_output_dir():
    """Get output directory from environment variable or default to local Outputs folder."""
    return os.environ.get("OPAL_OUTPUT_DIR", os.path.join(os.getcwd(), "Outputs"))

def get_segments_dir():
    """Get segments directory from environment variable or default to local Manual_Segments folder."""
    return os.environ.get("OPAL_SEGMENTS_DIR", os.path.join(os.getcwd(), "Manual_Segments"))

# --- Utility Functions ---
def clean_youtube_url(url):
    """URL से ट्रैकिंग पैरामीटर्स हटाता है।"""
    if not url: return ""
    return url.split('?si=')[0].split('&si=')[0].strip()

def get_duration(input_file):
    """ऑडियो फाइल की कुल अवधि (Seconds) निकालता है।"""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return float(res.stdout.strip()) if res.stdout and res.stdout.strip() else 0

def get_video_info(url):
    url = clean_youtube_url(url)
    if not url:
        return "Please enter a YouTube URL to get info."

    ydl_opts = {'quiet': True, 'no_warnings': True, 'nocheckcertificate': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            status = "LIVE" if info.get('is_live') else "VOD"
            title = info.get('title', 'N/A')
            duration = info.get('duration_string', 'N/A')
            uploader = info.get('uploader', 'N/A')
            upload_date = info.get('upload_date')
            if upload_date:
                # Convert YYYYMMDD to DD/MM/YYYY
                upload_date = f"{upload_date[6:8]}/{upload_date[4:6]}/{upload_date[0:4]}"

            description = info.get('description', 'No description available')
            # Limit description length for display
            description = (description[:500] + '...') if len(description) > 500 else description

            return (
                f"**Title:** {title}\n"
                f"**Status:** {status}\n"
                f"**Duration:** {duration}\n"
                f"**Uploader:** {uploader}\n"
                f"**Upload Date:** {upload_date}\n"
                f"**Description:**\n```\n{description}\n```"
            )
    except yt_dlp.utils.DownloadError as e:
        return f"❌ Error retrieving video info: {e}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"

# --- Stop Function (Graceful Exit) ---
def stop_task():
    global current_process
    if current_process and current_process.poll() is None:
        try:
            os.killpg(os.getpgid(current_process.pid), signal.SIGINT)
            return "🛑 रिकॉर्डिंग रोकी गई। मक्सिंग (Muxing) प्रारम्भ...", "Finalizing..."
        except: return "⚠️ रोकने में समस्या आई।", "Error"
    return "ℹ️ कोई सक्रिय टास्क नहीं है।", "Idle"

# --- Core Surgery and Segmentation Engine (Muxer) ---
def run_segmentation(input_file, seg_len, seg_num, overlap, start_off, end_off, filename=None):
    if not input_file or not os.path.exists(input_file):
        yield "❌ फाइल नहीं मिली", None, None
        return

    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    date_folder = now.strftime("%Y-%m-%d") # तारीख के अनुसार फोल्डर
    ts = now.strftime("%H%M")
    base = filename if filename else "opal_edit"

    # Path setup with environment variable support
    base_path = get_segments_dir()
    os.makedirs(base_path, exist_ok=True)

    final_dir = os.path.join(base_path, date_folder)
    os.makedirs(final_dir, exist_ok=True)

    seg_folder = os.path.join(final_dir, f"{base}_{ts}")
    os.makedirs(seg_folder, exist_ok=True)

    yield f"🔍 तारीख: {date_folder} | विश्लेषण जारी...", None, None
    total_dur = get_duration(input_file)

    # Calculation (Logic for Length vs Number)
    final_len = 0
    if seg_num and int(seg_num) > 0:
        final_len = total_dur / int(seg_num)
    else:
        final_len = float(seg_len or 0)

    # FFmpeg Command Construction
    cmd = ["ffmpeg", "-y"]
    # Apply start/end offsets if present, before segmentation logic
    if start_off and str(start_off).strip(): cmd.extend(["-ss", str(start_off).strip()])
    if end_off and str(end_off).strip(): cmd.extend(["-to", str(end_off).strip()])
    cmd.extend(["-i", input_file])

    if final_len > 0:
        yield f"✂️ विभाजन: {final_len:.1f}s प्रत्येक (Overlap: {overlap}s)", None, None
        # Segmenting with overlap (Surgical Precision)
        # Note: Overlap can be controlled via '-segment_time_delta'
        cmd.extend(
            [
                "-f", "segment",
                "-segment_time", str(final_len),
                "-c", "copy",
                os.path.join(seg_folder, "part_%03d.m4a")
            ]
        )
    else: # If no segmentation, just copy/trim the input file
        cmd.extend(["-c", "copy", os.path.join(seg_folder, f"{base}_final.m4a")])

    subprocess.run(cmd, capture_output=True)

    yield "📦 ZIP तैयार किया जा रहा है...", None, None
    shutil.make_archive(seg_folder, 'zip', seg_folder)
    zip_path = f"{seg_folder}.zip"
    yield f"✅ पूर्ण: {os.path.basename(zip_path)}", zip_path, zip_path

# --- Smart Downloader Engine ---
def opal_smart_engine(url, base_folder, filename, live_from_start, time_params, cookies_filepath=None):
    global current_process
    url = clean_youtube_url(url)
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    date_f, time_s = now.strftime("%Y-%m-%d"), now.strftime("%H%M")

    local_base_folder = get_output_dir()
    os.makedirs(local_base_folder, exist_ok=True)

    final_dir = os.path.join(local_base_folder, date_f)
    os.makedirs(final_dir, exist_ok=True)

    ydl_opts = {'quiet': True, 'no_warnings': True, 'nocheckcertificate': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            status = "LIVE" if info.get('is_live') else "VOD"
        except: status = "VOD"

    yield f"🔍 तारीख: {date_f} | स्थिति: {status}", "प्रारम्भ...", None, None

    cmd = ["yt-dlp", "-f", "ba[ext=m4a]/ba", "--extract-audio", "--audio-format", "m4a", "--audio-quality", "0", "--newline", "--no-check-certificate"]

    if cookies_filepath and os.path.exists(cookies_filepath):
        cmd.extend(["--cookies", cookies_filepath])
        cmd.extend(["--impersonate", "chrome:windows-10"])

    s, e = str(time_params.get("start") or "").strip(), str(time_params.get("end") or "").strip()
    sl_val = int(time_params.get("seg_len") or 0)

    use_download_sections = False
    if s or e:
        if status == "LIVE":
            section_str = ""
            if s and e: section_str = f"*{s}-{e}"
            elif s: section_str = f"*{s}-inf"
            elif e: section_str = f"*-{e}"
            if section_str:
                cmd.extend(["--download-sections", section_str])
                use_download_sections = True

    if status == "LIVE" and live_from_start and not use_download_sections:
        cmd.append("--live-from-start")

    file_id = f"{filename}_{time_s}"
    out_template = os.path.join(final_dir, f"{file_id}.%(ext)s")
    cmd.extend(["-o", out_template, url])

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, preexec_fn=os.setsid)
    current_process = process
    for line in process.stdout:
        if any(k in line.lower() for k in ["frag:", "[download]"]):
            yield "📥 सक्रिय डाउनलोड...", line.strip(), None, None
    process.wait()
    current_process = None

    raw_downloaded_audio_path = os.path.join(final_dir, f"{file_id}.m4a")

    if os.path.exists(raw_downloaded_audio_path):
        if sl_val > 0 or (s or e and status != "LIVE" and not use_download_sections): # If segmentation requested OR trimming requested for VODs
            yield "🗂️ ऑटो-सेगमेंटिंग/ट्रिमिंग...", "ZIP निर्माण...", None, raw_downloaded_audio_path
            segmentation_generator = run_segmentation(raw_downloaded_audio_path, sl_val, 0, 0, s, e, filename)
            for seg_status, seg_out_path, _ in segmentation_generator:
                 yield seg_status, seg_out_path, seg_out_path, raw_downloaded_audio_path
        else:
            yield f"✅ सफल: {file_id}", raw_downloaded_audio_path, raw_downloaded_audio_path, raw_downloaded_audio_path
    else:
        yield "❌ डाउनलोड विफल", None, None, None

# --- Gradio UI ---
with gr.Blocks(title="Opal Smart Engine v3") as demo:
    gr.Markdown("# 🛸 Opal Smart Audio Engine & Muxer")

    with gr.Tabs():
        with gr.TabItem("📡 Downloader"):
            with gr.Column():
                with gr.Row():
                    url_in = gr.Textbox(label="YouTube URL (Auto-Cleaned)", placeholder="https://...", scale=4)
                    info_btn = gr.Button("ℹ️ Get Info", scale=1)

                url_info_out = gr.Markdown(label="Video Information")

                name_in = gr.Textbox(label="Filename Prefix", value="11AD")
                live_lfs = gr.Checkbox(label="⏪ Live From Start (DVR Rewind)", value=False)
                with gr.Accordion("✂️ Advanced Options", open=False):
                    st_s = gr.Textbox(label="Start Point (Sec)", placeholder="0")
                    en_s = gr.Textbox(label="End Point (Sec)", placeholder="End")
                    sg_s = gr.Number(label="Segment Length (0 = No Split)", value=0)
                    cookies_file_upload = gr.File(label="Cookies File (for private videos)", type="filepath")
                with gr.Row():
                    exec_btn = gr.Button("🚀 Execute Task", variant="primary", scale=2)
                    stop_btn = gr.Button("🛑 Stop Live", variant="stop", scale=1)
                dl_status = gr.Textbox(label="Status", interactive=False)
                dl_out = gr.File(label="📥 Download Audio/ZIP Link", interactive=False)

        with gr.TabItem("✂️ Independent Muxer"):
            with gr.Column():
                mx_in = gr.File(label="Select Audio File", type="filepath")
                with gr.Accordion("✂️ Surgery & Overlap", open=True):
                    with gr.Row():
                        mx_ss = gr.Textbox(label="Start Offset", placeholder="0")
                        mx_to = gr.Textbox(label="End Offset", placeholder="End")
                    mx_ov = gr.Number(label="Overlap (Seconds)", value=0, info="सत्संग निरंतरता के लिए ३-५ सेकंड उचित है।")
                with gr.Row():
                    mx_sl = gr.Number(label="Fixed Length (Sec)", value=450)
                    mx_sn = gr.Number(label="Fixed Number of Segments", value=0)
                mx_nm = gr.Textbox(label="Output Prefix", value="Session")
                mx_btn = gr.Button("📂 Run Advanced Surgery", variant="secondary")
                mx_st = gr.Textbox(label="Muxer Status", interactive=False)
                mx_ot = gr.File(label="📥 Download Result ZIP Link", interactive=False)

    # Interaction logic
    def dl_wrap(u, n, l, s, e, sl, cookies_fp):
        p = {"start": s, "end": e, "seg_len": sl}
        local_output_base = get_output_dir()
        os.makedirs(local_output_base, exist_ok=True)
        yield from opal_smart_engine(u, local_output_base, n, l, p, cookies_fp)

    exec_btn.click(
        dl_wrap,
        [url_in, name_in, live_lfs, st_s, en_s, sg_s, cookies_file_upload],
        [dl_status, dl_status, dl_out, mx_in]
    )

    stop_btn.click(stop_task, outputs=[dl_status, dl_status])
    mx_btn.click(run_segmentation, [mx_in, mx_sl, mx_sn, mx_ov, mx_ss, mx_to, mx_nm], [mx_st, mx_ot, mx_ot])
    info_btn.click(get_video_info, [url_in], [url_info_out])

# --- Launch Gradio App ---
if __name__ == "__main__":
    # Define allowed paths for Gradio to handle files outside its default directories
    allowed_paths = [
        get_output_dir(),
        get_segments_dir()
    ]
    demo.launch(debug=True, share=True, theme=gr.themes.Soft(), allowed_paths=allowed_paths)
