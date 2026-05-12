
import os, subprocess, shutil, yt_dlp, pytz, re, signal
from datetime import datetime
import gradio as gr

# --- Global Variables ---
current_process = None

# --- Utility Functions ---
def clean_youtube_url(url):
    '''Removes tracking parameters from a URL.'''
    if not url: return ""
    return url.split('?si=')[0].split('&si=')[0].strip()

def get_duration(input_file):
    '''Gets the total duration of an audio file (in seconds).'''
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
                f"**Title:** {title}"
                f"**Status:** {status}"
                f"**Uploader:** {uploader}"
                f"**Upload Date:** {upload_date}"
                f"**Duration:** {duration}"
                f"**Description:** {description}"
            )
    except Exception as e:
        return f"Error getting video info: {e}"

# --- Opal Smart Engine ---
# This is a placeholder. You'd replace this with your actual opal_smart_engine implementation
def opal_smart_engine(url, output_base, name, live_lfs, params, cookies_fp):
    '''
    Simulates the core logic for downloading and processing audio.
    In a real application, this would handle yt-dlp calls, segmentation, etc.
    '''
    print(f"Processing URL: {url} with name: {name}")
    print(f"Live/LFS: {live_lfs}, Params: {params}, Cookies: {cookies_fp}")
    print(f"Output will be saved to: {output_base}")

    # Simulate some work
    import time
    time.sleep(2)
    
    # Create dummy output files
    os.makedirs(output_base, exist_ok=True)
    dummy_audio_file = os.path.join(output_base, f"{name}_audio.mp3")
    dummy_zip_file = os.path.join(output_base, f"{name}_segments.zip")
    with open(dummy_audio_file, "w") as f:
        f.write("dummy audio content")
    with open(dummy_zip_file, "w") as f:
        f.write("dummy zip content")

    yield "Processing complete. See dummy files.", "", dummy_audio_file, dummy_zip_file

def run_segmentation(input_file, seg_len, num_segments, overlap, start_offset, end_offset, output_prefix):
    '''
    Simulates the segmentation logic.
    In a real application, this would use ffmpeg or similar for segmentation.
    '''
    print(f"Segmenting file: {input_file}")
    print(f"Length: {seg_len}, Number: {num_segments}, Overlap: {overlap}")
    print(f"Offsets: Start={start_offset}, End={end_offset}, Prefix={output_prefix}")

    # Simulate some work
    import time
    time.sleep(2)

    base_path = os.environ.get("OPAL_SEGMENTS_DIR", os.path.join(os.getcwd(), "Manual_Segments"))
    os.makedirs(base_path, exist_ok=True)
    dummy_output_zip = os.path.join(base_path, f"{output_prefix}_segments.zip")
    with open(dummy_output_zip, "w") as f:
        f.write("dummy segmented zip content")
    
    return "Segmentation complete. See dummy zip.", dummy_output_zip, dummy_output_zip


# --- Gradio Interface ---
#with gr.Blocks(theme=gr.themes.Soft()) as demo:
with gr.Blocks() as demo:
    gr.Markdown("# YouTube Audio Downloader & Muxer (Opal Edition)")

    with gr.TabItem("▶️ Live Downloader"):
        with gr.Column():
            url_in = gr.Textbox(label="YouTube Video URL", placeholder="Enter YouTube URL here...")
            info_btn = gr.Button("ℹ️ Get Video Info", variant="primary")
            url_info_out = gr.Textbox(label="Video Information", interactive=False)
            name_in = gr.Textbox(label="Output File Name", placeholder="Optional: Enter a custom name. Default is video title.")
            live_lfs = gr.Checkbox(label="Live/LFS (Download Best Audio + Video)", info="Long Form Content")
            cookies_file_upload = gr.File(label="Upload Cookies File (optional)", type="filepath", file_count="single", file_types=[".txt"])

            with gr.Accordion("⚙️ Advanced Download Options", open=False):
                with gr.Row():
                    st_s = gr.Textbox(label="Start (HH:MM:SS)", placeholder="00:00:00")
                    en_s = gr.Textbox(label="End (HH:MM:SS)", placeholder="End")
                    sg_s = gr.Number(label="Segment Length (Seconds)", value=0, info="0 for full video")

            with gr.Row():
                exec_btn = gr.Button("🚀 Download & Process", variant="primary", scale=2)
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
                mx_ov = gr.Number(label="Overlap (Seconds)", value=0, info="Optimal for continuous satsang: 3-5 seconds.")
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
        local_output_base = os.environ.get("OPAL_OUTPUT_DIR", os.path.join(os.getcwd(), "Outputs"))
        os.makedirs(local_output_base, exist_ok=True)
        yield from opal_smart_engine(u, local_output_base, n, l, p, cookies_fp)

    def stop_task():
        # Placeholder for actual stop logic
        print("Stopping task...")
        return "Task stopped.", "Task stopped."

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
    #demo.launch(debug=True, share=False, theme=gr.themes.Soft())
    demo.launch(debug=True, share=True, theme=gr.themes.Soft())
