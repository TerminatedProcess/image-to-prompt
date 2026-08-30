# app.py
import streamlit as st
import streamlit.components.v1 as components
import os
import json
import uuid
import copy 
from datetime import datetime
from pathlib import Path
import html
import re

# --- Local Imports ---
import config_manager as cm
from api_client import APIClient
from bulk_analyzer import bulk_analysis_page
from metadata_extractor import ImageMetadataExtractor
import image_backends
from refine_engine import REFINE_SYSTEM, build_user_message, parse_verdict

# --- Constants from joycaption ---
CAPTION_TYPE_MAP = {
	"Descriptive": [
		"Write a detailed description for this image.",
		"Write a detailed description for this image in {word_count} words or less.",
		"Write a {length} detailed description for this image.",
	],
	"Descriptive (Casual)": [
		"Write a descriptive caption for this image in a casual tone.",
		"Write a descriptive caption for this image in a casual tone within {word_count} words.",
		"Write a {length} descriptive caption for this image in a casual tone.",
	],
	"Straightforward": [
		"Write a straightforward caption for this image. Begin with the main subject and medium. Mention pivotal elements—people, objects, scenery—using confident, definite language. Focus on concrete details like color, shape, texture, and spatial relationships. Show how elements interact. Omit mood and speculative wording. If text is present, quote it exactly. Note any watermarks, signatures, or compression artifacts. Never mention what's absent, resolution, or unobservable details. Vary your sentence structure and keep the description concise, without starting with \"This image is...\" or similar phrasing.",
		"Write a straightforward caption for this image within {word_count} words. Begin with the main subject and medium. Mention pivotal elements—people, objects, scenery—using confident, definite language. Focus on concrete details like color, shape, texture, and spatial relationships. Show how elements interact. Omit mood and speculative wording. If text is present, quote it exactly. Note any watermarks, signatures, or compression artifacts. Never mention what's absent, resolution, or unobservable details. Vary your sentence structure and keep the description concise, without starting with \"This image is...\" or similar phrasing.",
		"Write a {length} straightforward caption for this image. Begin with the main subject and medium. Mention pivotal elements—people, objects, scenery—using confident, definite language. Focus on concrete details like color, shape, texture, and spatial relationships. Show how elements interact. Omit mood and speculative wording. If text is present, quote it exactly. Note any watermarks, signatures, or compression artifacts. Never mention what's absent, resolution, or unobservable details. Vary your sentence structure and keep the description concise, without starting with \"This image is...\" or similar phrasing.",
	],
	"Stable Diffusion Prompt": [
		"Output a stable diffusion prompt that is indistinguishable from a real stable diffusion prompt.",
		"Output a stable diffusion prompt that is indistinguishable from a real stable diffusion prompt. {word_count} words or less.",
		"Output a {length} stable diffusion prompt that is indistinguishable from a real stable diffusion prompt.",
	],
	"MidJourney": [
		"Write a MidJourney prompt for this image.",
		"Write a MidJourney prompt for this image within {word_count} words.",
		"Write a {length} MidJourney prompt for this image.",
	],
	"Danbooru tag list": [
		"Generate only comma-separated Danbooru tags (lowercase_underscores). Strict order: `artist:`, `copyright:`, `character:`, `meta:`, then general tags. Include counts (1girl), appearance, clothing, accessories, pose, expression, actions, background. Use precise Danbooru syntax. No extra text.",
		"Generate only comma-separated Danbooru tags (lowercase_underscores). Strict order: `artist:`, `copyright:`, `character:`, `meta:`, then general tags. Include counts (1girl), appearance, clothing, accessories, pose, expression, actions, background. Use precise Danbooru syntax. No extra text. {word_count} words or less.",
		"Generate only comma-separated Danbooru tags (lowercase_underscores). Strict order: `artist:`, `copyright:`, `character:`, `meta:`, then general tags. Include counts (1girl), appearance, clothing, accessories, pose, expression, actions, background. Use precise Danbooru syntax. No extra text. {length} length.",
	],
	"e621 tag list": [
		"Write a comma-separated list of e621 tags in alphabetical order for this image. Start with the artist, copyright, character, species, meta, and lore tags (if any), prefixed by 'artist:', 'copyright:', 'character:', 'species:', 'meta:', and 'lore:'. Then all the general tags.",
		"Write a comma-separated list of e621 tags in alphabetical order for this image. Start with the artist, copyright, character, species, meta, and lore tags (if any), prefixed by 'artist:', 'copyright:', 'character:', 'species:', 'meta:', and 'lore:'. Then all the general tags. Keep it under {word_count} words.",
		"Write a {length} comma-separated list of e621 tags in alphabetical order for this image. Start with the artist, copyright, character, species, meta, and lore tags (if any), prefixed by 'artist:', 'copyright:', 'character:', 'species:', 'meta:', and 'lore:'. Then all the general tags.",
	],
	"Rule34 tag list": [
		"Write a comma-separated list of rule34 tags in alphabetical order for this image. Start with the artist, copyright, character, and meta tags (if any), prefixed by 'artist:', 'copyright:', 'character:', and 'meta:'. Then all the general tags.",
		"Write a comma-separated list of rule34 tags in alphabetical order for this image. Start with the artist, copyright, character, and meta tags (if any), prefixed by 'artist:', 'copyright:', 'character:', and 'meta:'. Then all the general tags. Keep it under {word_count} words.",
		"Write a {length} comma-separated list of rule34 tags in alphabetical order for this image. Start with the artist, copyright, character, and meta tags (if any), prefixed by 'artist:', 'copyright:', 'character:', and 'meta:'. Then all the general tags.",
	],
	"Booru-like tag list": [
		"Write a list of Booru-like tags for this image.",
		"Write a list of Booru-like tags for this image within {word_count} words.",
		"Write a {length} list of Booru-like tags for this image.",
	],
	"Art Critic": [
		"Analyze this image like an art critic would with information about its composition, style, symbolism, the use of color, light, any artistic movement it might belong to, etc.",
		"Analyze this image like an art critic would with information about its composition, style, symbolism, the use of color, light, any artistic movement it might belong to, etc. Keep it within {word_count} words.",
		"Analyze this image like an art critic would with information about its composition, style, symbolism, the use of color, light, any artistic movement it might belong to, etc. Keep it {length}.",
	],
	"Product Listing": [
		"Write a caption for this image as though it were a product listing.",
		"Write a caption for this image as though it were a product listing. Keep it under {word_count} words.",
		"Write a {length} caption for this image as though it were a product listing.",
	],
	"Social Media Post": [
		"Write a caption for this image as if it were being used for a social media post.",
		"Write a caption for this image as if it were being used for a social media post. Limit the caption to {word_count} words.",
		"Write a {length} caption for this image as if it were being used for a social media post.",
	],
}
NAME_OPTION = "If there is a person/character in the image you must refer to them as {name}."

# --- System Prompt Builder options (module-level so callbacks can map them too) ---
EXTRA_OPTIONS_KEYS = [
    NAME_OPTION,
    "Do NOT include information about people/characters that cannot be changed (like ethnicity, gender, etc), but do still include changeable attributes (like hair style).",
    "Include information about lighting.",
    "Include information about camera angle.",
    "Include information about whether there is a watermark or not.",
    "Include information about whether there are JPEG artifacts or not.",
    "If it is a photo you MUST include information about what camera was likely used and details such as aperture, shutter speed, ISO, etc.",
    "Do NOT include anything sexual; keep it PG.",
    "Do NOT mention the image's resolution.",
    "You MUST include information about the subjective aesthetic quality of the image from low to very high.",
    "Include information on the image's composition style, such as leading lines, rule of thirds, or symmetry.",
    "Do NOT mention any text that is in the image.",
    "Specify the depth of field and whether the background is in focus or blurred.",
    "If applicable, mention the likely use of artificial or natural lighting sources.",
    "Do NOT use any ambiguous language.",
    "Include whether the image is sfw, suggestive, or nsfw.",
    "ONLY describe the most important elements of the image.",
    "If it is a work of art, do not include the artist's name or the title of the work.",
    "Identify the image orientation (portrait, landscape, or square) and aspect ratio if obvious.",
    "Use vulgar slang and profanity (such as, but not limited to, \"fucking,\" \"slut,\" \"cock,\") ONLY when it refers to something sexual — the person, their body or body parts, their clothing, their pose or actions, or the erotic mood/ambience of the scene. Do NOT apply vulgar language to neutral or technical subjects such as the camera, lens, lighting equipment, resolution, composition, or scenery that has no sexual connotation.",
    "Do NOT use polite euphemisms—lean into blunt, casual phrasing.",
    "Include information about the ages of any people/characters when applicable.",
    "Mention whether the image depicts an extreme close-up, close-up, medium close-up, medium shot, cowboy shot, medium wide shot, wide shot, or extreme wide shot.",
    "Do not mention the mood/feeling/etc of the image.",
    "Explicitly specify the vantage height (eye-level, low-angle worm’s-eye, bird’s-eye, drone, rooftop, etc.).",
    "If there is a watermark, you must mention it.",
    'Your response will be used by a text-to-image model, so avoid useless meta phrases like \“This image shows…\", \“You are looking at...\", etc.',
    "Always state the subject's hair color, length, and style, plus eye color and skin tone.",
]

def _current_builder_config():
    """Snapshot the builder widget state into a serializable dict."""
    return {
        "caption_type": st.session_state.get("modal_caption_type", list(CAPTION_TYPE_MAP.keys())[0]),
        "caption_length": st.session_state.get("modal_caption_length", "any"),
        "options": [opt for i, opt in enumerate(EXTRA_OPTIONS_KEYS)
                    if st.session_state.get(f"modal_extra_option_{i}", False)],
        "name_input": st.session_state.get("modal_name_input", ""),
    }

def apply_builder_config(cfg):
    """Push a saved builder config back into the widget session_state keys.

    Must run BEFORE the builder widgets are instantiated this run (i.e. from an
    on_change callback or init), otherwise Streamlit raises on mutating a
    widget-backed key after the widget exists.
    """
    if not cfg:
        return
    if cfg.get("caption_type") in CAPTION_TYPE_MAP:
        st.session_state["modal_caption_type"] = cfg["caption_type"]
    if "caption_length" in cfg:
        st.session_state["modal_caption_length"] = cfg["caption_length"]
    selected = set(cfg.get("options", []))
    for i, opt in enumerate(EXTRA_OPTIONS_KEYS):
        st.session_state[f"modal_extra_option_{i}"] = opt in selected
    st.session_state["modal_name_input"] = cfg.get("name_input", "")

# --- Page Configuration ---
st.set_page_config(
    page_title="Image-to-Prompt AI Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Initialize Session State ---
def init_session_state():
    if "messages" not in st.session_state: st.session_state.messages = []
    if "chat_id" not in st.session_state: st.session_state.chat_id = None
    if "config" not in st.session_state: st.session_state.config = cm.load_config()
    if "system_prompts" not in st.session_state: st.session_state.system_prompts = cm.load_system_prompts()
    if "current_system_prompt" not in st.session_state:
        last_prompt_name = st.session_state.config.get("last_system_prompt_name", "Default Image-to-Prompt")
        st.session_state.current_system_prompt = st.session_state.system_prompts.get(last_prompt_name, st.session_state.system_prompts.get("Default Image-to-Prompt", ""))
        st.session_state.current_system_prompt_name = last_prompt_name
    if "system_prompt_text_area" not in st.session_state:
        st.session_state["system_prompt_text_area"] = st.session_state.current_system_prompt
    if "uploaded_files" not in st.session_state: st.session_state.uploaded_files = []
    if "uploaded_videos" not in st.session_state: st.session_state.uploaded_videos = []
    if "metadata_extractor" not in st.session_state: st.session_state.metadata_extractor = ImageMetadataExtractor()
    
    if "uploader_key" not in st.session_state: st.session_state.uploader_key = str(uuid.uuid4())
    if "generating" not in st.session_state:
        st.session_state.generating = False
    if "builder_configs" not in st.session_state:
        st.session_state.builder_configs = cm.load_builder_configs()
    if "builder_restored" not in st.session_state:
        # Restore the last-used builder state once per session, before the
        # builder widgets are instantiated further down the script.
        apply_builder_config(st.session_state.builder_configs.get("__last__"))
        st.session_state.builder_restored = True
    # --- Compare & refine (Resulting Images) state ---
    if "result_uploader_key" not in st.session_state: st.session_state.result_uploader_key = str(uuid.uuid4())
    if "last_result_sig" not in st.session_state: st.session_state.last_result_sig = None
    if "refine_error" not in st.session_state: st.session_state.refine_error = None
    if "refine_retry" not in st.session_state: st.session_state.refine_retry = None
    if "refine_backend_obj" not in st.session_state: st.session_state.refine_backend_obj = None
    if "auto_running" not in st.session_state: st.session_state.auto_running = False
    if "auto_iter" not in st.session_state: st.session_state.auto_iter = 0
    if "auto_stop" not in st.session_state: st.session_state.auto_stop = False
    if "plateau_count" not in st.session_state: st.session_state.plateau_count = 0
    if "auto_summary" not in st.session_state: st.session_state.auto_summary = ""
    if "auto_phase" not in st.session_state: st.session_state.auto_phase = "fixed"
    if "fixed_seed" not in st.session_state: st.session_state.fixed_seed = None

init_session_state()

def remove_thinking_tags(text):
    """Removes <think>...</think> tags from a string."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

# --- Helper & Chat Management Functions ---
def save_uploaded_file(uploaded_file):
    temp_dir = Path("temp_images"); temp_dir.mkdir(exist_ok=True)
    file_path = temp_dir / f"{uuid.uuid4()}_{uploaded_file.name}"
    original_name = uploaded_file.name
    with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return (file_path, original_name)

def save_uploaded_video(uploaded_file):
    temp_dir = Path("temp_videos"); temp_dir.mkdir(exist_ok=True)
    file_path = temp_dir / f"{uuid.uuid4()}_{uploaded_file.name}"
    original_name = uploaded_file.name
    with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return (file_path, original_name)

def is_video_file(filename):
    """Check if the file is a supported video format."""
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
    return Path(filename).suffix.lower() in video_extensions

def extract_ai_prompts_from_metadata(metadata):
    """Extract prompt and negative prompt from AI metadata."""
    if not metadata:
        return None, None
    
    prompt = None
    negative_prompt = None
    
    # Function to parse structured prompt data (like from AUTOMATIC1111)
    def parse_structured_prompt(text_data):
        nonlocal prompt, negative_prompt
        if 'Negative prompt:' in text_data:
            # Split on "Negative prompt:" to separate positive and negative
            parts = text_data.split('Negative prompt:', 1)
            if len(parts) == 2:
                # Extract positive prompt (everything before "Negative prompt:")
                positive_part = parts[0].strip()
                # Remove any leading labels like "Prompt:" or similar
                if positive_part.startswith(('Prompt:', 'prompt:')):
                    positive_part = positive_part.split(':', 1)[1].strip()
                if not prompt and positive_part:
                    prompt = positive_part
                
                # Extract negative prompt (everything after "Negative prompt:" until next parameter)
                negative_part = parts[1].strip()
                # Find where parameters start (usually indicated by newline + parameter name)
                param_indicators = ['\nSteps:', '\nSampler:', '\nCFG scale:', '\nSeed:', '\nSize:', '\nModel:', '\nClip skip:']
                for indicator in param_indicators:
                    if indicator in negative_part:
                        negative_part = negative_part.split(indicator)[0].strip()
                        break
                if not negative_prompt and negative_part:
                    negative_prompt = negative_part
        elif not prompt and len(text_data) > 20:  # If no structured format, use as prompt
            prompt = text_data
    
    # Priority 1: Check PNG text data (most common for AI images)
    if metadata.get('png_text'):
        png_data = metadata['png_text']
        # Check for parameters field (AUTOMATIC1111 format)
        if 'parameters' in png_data:
            parse_structured_prompt(str(png_data['parameters']))
        
        # Check for direct prompt fields
        if not prompt and 'prompt' in png_data:
            prompt = str(png_data['prompt'])
        if not negative_prompt and 'negative_prompt' in png_data:
            negative_prompt = str(png_data['negative_prompt'])
    
    # Priority 2: Check AI metadata if not found in PNG text
    if (not prompt or not negative_prompt) and metadata.get('ai_metadata'):
        ai_data = metadata['ai_metadata']
        for key, value in ai_data.items():
            key_lower = key.lower()
            if 'prompt' in key_lower and 'negative' not in key_lower and not prompt:
                prompt = str(value)
            elif 'negative' in key_lower and 'prompt' in key_lower and not negative_prompt:
                negative_prompt = str(value)
            elif key_lower in ['user_comment', 'ai prompt/parameters'] and (not prompt or not negative_prompt):
                parse_structured_prompt(str(value))
    
    # Priority 3: Check Windows properties if still not found
    if (not prompt or not negative_prompt) and metadata.get('windows_properties'):
        for key, value in metadata['windows_properties'].items():
            if value and len(str(value)) > 20:
                parse_structured_prompt(str(value))
                if prompt and negative_prompt:  # Stop if we found both
                    break
    
    return prompt, negative_prompt


def display_image_metadata(image_path, original_name):
    """Display image metadata in an expandable section."""
    # Check if the file is a PNG - only extract metadata for PNG files
    file_extension = Path(image_path).suffix.lower()
    if file_extension not in ['.png']:
        # For non-PNG files, show a simple message
        with st.expander(f"📊 View Metadata - {original_name}", expanded=False):
            st.info(f"Metadata extraction is only supported for PNG files. This is a {file_extension.upper()} file.")
        return
    
    metadata = st.session_state.metadata_extractor.extract_metadata(image_path)
    
    if metadata:
        formatted_sections = st.session_state.metadata_extractor.format_metadata_for_display(metadata)
        
        if formatted_sections:
            with st.expander(f"📊 View Metadata - {original_name}", expanded=False):
                for idx, section in enumerate(formatted_sections):
                    # Determine CSS class based on section title
                    css_class = "metadata-section"
                    if "AI Generation" in section['title']:
                        css_class += " ai-metadata"
                    elif "Technical" in section['title']:
                        css_class += " technical-metadata"
                    elif "File Information" in section['title']:
                        css_class += " file-metadata"
                    
                    # Create a styled container for each section
                    st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
                    st.markdown(f'<div class="metadata-title">{section["title"]}</div>', unsafe_allow_html=True)
                    
                    # Display content in a nice format
                    for key, value in section['content'].items():
                        # Handle long text values (like prompts)
                        if len(str(value)) > 100:
                            st.markdown(f'<div class="metadata-item"><span class="metadata-key">{key}:</span></div>', unsafe_allow_html=True)
                            st.code(str(value), language=None)
                        else:
                            # Truncate very long values for display
                            display_value = str(value)
                            if len(display_value) > 50:
                                display_value = display_value[:47] + "..."
                            st.markdown(f'<div class="metadata-item"><span class="metadata-key">{key}:</span> <span class="metadata-value">{html.escape(display_value)}</span></div>', unsafe_allow_html=True)
                    

                    
                    st.markdown('</div>', unsafe_allow_html=True)
                    st.write("")  # Add some spacing
        else:
            with st.expander(f"📊 View Metadata - {original_name}", expanded=False):
                st.info("No AI generation metadata found in this image.")
    else:
        with st.expander(f"📊 View Metadata - {original_name}", expanded=False):
            st.error("Could not extract metadata from this image.")

def auto_save_chat():
    if not st.session_state.messages: return
    if st.session_state.chat_id is None:
        first_user_message = next((msg['content'] for msg in st.session_state.messages if msg['role'] == 'user'), 'New Chat')
        safe_title = "".join(c for c in first_user_message if c.isalnum() or c in " ._").rstrip()[:50]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        st.session_state.chat_id = f"{safe_title}_{timestamp}.json"
    cm.save_conversation(st.session_state.chat_id, st.session_state.messages)

def reset_refine_state():
    st.session_state.last_result_sig = None
    st.session_state.result_uploader_key = str(uuid.uuid4())
    st.session_state.refine_error = None
    st.session_state.refine_retry = None
    st.session_state.auto_running = False
    st.session_state.auto_iter = 0
    st.session_state.auto_stop = False
    st.session_state.plateau_count = 0
    st.session_state.auto_summary = ""
    st.session_state.auto_phase = "fixed"
    st.session_state.fixed_seed = None

def start_new_chat():
    st.session_state.messages = []; st.session_state.chat_id = None; st.session_state.uploaded_files = []
    st.session_state.uploaded_videos = []; st.session_state.uploader_key = str(uuid.uuid4())
    reset_refine_state()

def load_chat_callback():
    selected_chat_file = st.session_state.get("selected_chat")
    if selected_chat_file:
        filepath = cm.CONVERSATIONS_DIR / selected_chat_file
        st.session_state.messages = cm.load_conversation(filepath)
        st.session_state.chat_id = selected_chat_file
        st.session_state.uploaded_files = []; st.session_state.uploaded_videos = []
        st.session_state.uploader_key = str(uuid.uuid4())
        reset_refine_state()

# <<< The `regenerate_last_response` function has been REMOVED >>>
def run_generation_logic():
    try:
        last_user_message = st.session_state.messages[-1]
        image_info = last_user_message.get("images", [])
        image_paths = [Path(info["path"]) for info in image_info]
        video_info = last_user_message.get("videos", [])
        video_paths = [Path(info["path"]) for info in video_info]
        api_messages = [{"role": "system", "content": st.session_state.current_system_prompt}]
        for msg in st.session_state.messages:
            if msg['role'] != 'system': api_messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Create APIClient with current provider settings
        current_provider_name = st.session_state.config["api_provider"]
        provider_config = st.session_state.config["providers"].get(current_provider_name, {})
        
        minicpm_config = None
        if current_provider_name == "MiniCPM":
            minicpm_config = provider_config
        
        api_client = APIClient(
            provider=current_provider_name,
            base_url=provider_config.get("api_base_url") if current_provider_name not in ["Google", "MiniCPM"] else None,
            google_api_key=st.session_state.config.get("google_api_key") if current_provider_name == "Google" else None,
            ollama_keep_alive=provider_config.get("keep_alive") if current_provider_name == "Ollama" else None,
            unload_after_response=provider_config.get("unload_after_response", False) if current_provider_name in ("LM Studio", "Unsloth") else provider_config.get("auto_unload", False) if current_provider_name == "MiniCPM" else False,
            minicpm_config=minicpm_config,
            api_key=provider_config.get("api_key") if current_provider_name == "Unsloth" else None
        )

        for model in st.session_state.config["providers"][st.session_state.config["api_provider"]]["selected_models"]:
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                prefix = f"**Response from `{model}`:**\n\n"
                message_placeholder.markdown(prefix + "▌")
                
                full_response = ""
                try:
                    messages_for_this_model = copy.deepcopy(api_messages)
                    stream_generator = api_client.generate_chat_response(model=model, messages=messages_for_this_model, images=image_paths, videos=video_paths)
                    for chunk in stream_generator:
                        full_response += chunk
                        # Filter out thinking tags before displaying
                        cleaned_response = remove_thinking_tags(full_response)
                        message_placeholder.markdown(prefix + cleaned_response + "▌")
                    # Final cleanup before saving
                    full_response = remove_thinking_tags(full_response)
                    message_placeholder.markdown(prefix + full_response)
                except Exception as e:
                    st.error(f"An error occurred with model {model}: {e}"); full_response = f"Error: {e}"
                    message_placeholder.markdown(prefix + full_response)
                
                display_response = prefix + full_response
                assistant_message = {"role": "assistant", "content": full_response, "display_content": display_response, "model": model, "id": str(uuid.uuid4())}
                st.session_state.messages.append(assistant_message)
                auto_save_chat()

    finally:
        st.session_state.generating = False
        # <<< CHANGE: The lines that cleared uploaded_files and reset the uploader_key have been REMOVED >>>
        # This makes the uploaded images persist for re-analysis.
        st.rerun()

def process_and_send_message(prompt_text, uploaded_file_info, uploaded_video_info=None):
    current_provider_name = st.session_state.config.get("api_provider", "Ollama") # Get current provider
    selected_models = st.session_state.config["providers"].get(current_provider_name, {}).get("selected_models", [])
    if not selected_models: st.error("Please select at least one model from the sidebar."); return

    image_info_for_message = [{"path": str(info[0]), "name": info[1]} for info in uploaded_file_info]
    video_info_for_message = [{"path": str(info[0]), "name": info[1]} for info in uploaded_video_info] if uploaded_video_info else []
    
    has_media = bool(image_info_for_message or video_info_for_message)
    is_media_only_request = not prompt_text.strip()
    
    if is_media_only_request and has_media:
        if video_info_for_message:
            internal_prompt = "Analyze the attached video(s) and image(s) according to the system prompt." if image_info_for_message else "Analyze the attached video(s) according to the system prompt."
        else:
            internal_prompt = "Analyze the attached image(s) according to the system prompt."
    else:
        internal_prompt = prompt_text
    
    display_text = prompt_text
    user_message = {"role": "user", "content": internal_prompt, "display_content": display_text, "id": str(uuid.uuid4())}
    if image_info_for_message: user_message["images"] = image_info_for_message
    if video_info_for_message: user_message["videos"] = video_info_for_message
    
    st.session_state.messages.append(user_message)
    auto_save_chat()
    st.session_state.generating = True
    st.rerun()

# ======================= Compare & Refine (Resulting Images) =======================
def make_api_client():
    """Build an APIClient for the current provider (mirrors run_generation_logic)."""
    provider = st.session_state.config["api_provider"]
    pconf = st.session_state.config["providers"].get(provider, {})
    minicpm_config = pconf if provider == "MiniCPM" else None
    return APIClient(
        provider=provider,
        base_url=pconf.get("api_base_url") if provider not in ["Google", "MiniCPM"] else None,
        google_api_key=st.session_state.config.get("google_api_key") if provider == "Google" else None,
        ollama_keep_alive=pconf.get("keep_alive") if provider == "Ollama" else None,
        unload_after_response=pconf.get("unload_after_response", False) if provider in ("LM Studio", "Unsloth") else pconf.get("auto_unload", False) if provider == "MiniCPM" else False,
        minicpm_config=minicpm_config,
        api_key=pconf.get("api_key") if provider == "Unsloth" else None,
    )

def get_starting_image_paths():
    return [Path(p) for (p, _name) in st.session_state.uploaded_files]

def _last_analysis_index():
    """Index of the most recent *normal* (non-refine) assistant analysis, or None.

    Skips refine verdicts and generated-image messages (which carry an image but
    empty content) so the loop's baseline prompt is a real caption, not a blank.
    """
    msgs = st.session_state.messages
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.get("role") == "assistant" and not m.get("refine") and (m.get("content") or "").strip():
            return i
    return None

def refine_entries():
    """Refine steps for the CURRENT target only — those after the latest analysis.

    Scoping to the current analysis means uploading a new starting image and
    re-analyzing starts a fresh refine history instead of mixing in the old
    target's prompts, results, and gallery.
    """
    msgs = st.session_state.messages
    base = _last_analysis_index()
    start = (base + 1) if base is not None else 0
    return [m["refine_data"] for m in msgs[start:] if m.get("refine")]

def refine_history():
    return [{"prompt": e["used_prompt"], "assessment": e["assessment"]} for e in refine_entries()]

def last_result_path():
    entries = refine_entries()
    if entries:
        p = Path(entries[-1]["result_path"])
        return p if p.exists() else None
    return None

def refine_done_flag():
    entries = refine_entries()
    return bool(entries) and entries[-1]["decision"] == "DONE"

def current_best_prompt():
    entries = refine_entries()
    if entries:
        return entries[-1]["next_prompt"]
    base = _last_analysis_index()
    if base is not None:
        return st.session_state.messages[base].get("content", "")
    return ""

def run_vision_review(target_paths, prev_path, new_path, current_prompt):
    """Send [targets..., prev?, new] to the vision model and parse its verdict."""
    provider = st.session_state.config["api_provider"]
    models = st.session_state.config["providers"].get(provider, {}).get("selected_models", [])
    if not models:
        raise RuntimeError("Select a vision model in the sidebar first.")
    images = [Path(p) for p in target_paths]
    if prev_path:
        images.append(Path(prev_path))
    images.append(Path(new_path))
    user_msg = build_user_message(current_prompt, refine_history(), n_targets=len(target_paths), has_prev=bool(prev_path))
    api_messages = [{"role": "system", "content": REFINE_SYSTEM}, {"role": "user", "content": user_msg}]
    client = make_api_client()
    full = ""
    for chunk in client.generate_chat_response(model=models[0], messages=copy.deepcopy(api_messages), images=images, videos=[]):
        full += chunk
    return parse_verdict(remove_thinking_tags(full), fallback_prompt=current_prompt)

def record_refine_step(new_path, new_name, used_prompt, verdict, source, seed=None):
    targets = get_starting_image_paths()
    prev = last_result_path()
    imgs = [{"path": str(p), "name": p.name} for p in targets]
    if prev:
        imgs.append({"path": str(prev), "name": "previous attempt"})
    imgs.append({"path": str(new_path), "name": new_name})
    st.session_state.messages.append({
        "role": "user", "content": f"[Refine: {source}] Compare the newest result to the target image(s).",
        "display_content": f"🔁 **Refine step** ({source})", "images": imgs, "id": str(uuid.uuid4()),
    })
    verdict_text = (
        f"**Assessment:** {verdict['assessment']}\n\n"
        f"**Decision:** `{verdict['decision']}`\n\n"
        f"**Next prompt:**\n\n{verdict['prompt']}"
    )
    st.session_state.messages.append({
        "role": "assistant", "content": verdict["prompt"], "display_content": verdict_text,
        "model": "refine", "id": str(uuid.uuid4()), "refine": True,
        "refine_data": {
            "result_path": str(new_path), "result_name": new_name, "used_prompt": used_prompt,
            "next_prompt": verdict["prompt"], "decision": verdict["decision"], "assessment": verdict["assessment"],
            "seed": seed,
        },
    })
    auto_save_chat()

def _norm_prompt(s):
    return " ".join((s or "").split()).lower()

def update_after_verdict(verdict, used_prompt):
    # A round only counts as progress when the model says IMPROVE *and* actually
    # changed the prompt. REVERT, DONE, or IMPROVE-without-change all count as
    # non-improving, so "stop after N non-improving rounds" behaves as labelled.
    changed = _norm_prompt(verdict["prompt"]) != _norm_prompt(used_prompt)
    if verdict["decision"] == "IMPROVE" and changed:
        st.session_state.plateau_count = 0
    else:
        st.session_state.plateau_count += 1

def do_refine_from_result(new_path, new_name, source):
    targets = get_starting_image_paths()
    prompt = current_best_prompt()
    prev = last_result_path()
    with st.spinner("Reviewing result against the target…"):
        verdict = run_vision_review(targets, prev, new_path, prompt)
    record_refine_step(new_path, new_name, prompt, verdict, source)
    update_after_verdict(verdict, prompt)

def _search_seed(obj):
    """Recursively hunt a seed value in an extracted-metadata structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in ("seed", "noise_seed") and isinstance(v, (int, str)):
                try:
                    return int(str(v).strip())
                except ValueError:
                    pass
            found = _search_seed(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _search_seed(item)
            if found is not None:
                return found
    return None

def get_target_seed():
    """Seed embedded in the first starting image's metadata, or None."""
    targets = get_starting_image_paths()
    if not targets:
        return None
    try:
        md = st.session_state.metadata_extractor.extract_metadata(str(targets[0]))
        return _search_seed(md)
    except Exception:
        return None

def get_or_create_backend(backend_id):
    obj = st.session_state.refine_backend_obj
    if obj is None or getattr(obj, "id", None) != backend_id:
        obj = image_backends.get_backend(backend_id)
        st.session_state.refine_backend_obj = obj
    return obj

def stop_auto(summary):
    st.session_state.auto_running = False
    st.session_state.auto_summary = summary

def start_auto_loop():
    import random
    backend = get_or_create_backend(st.session_state.get("refine_backend", "invokeai"))
    try:
        backend.prepare()
    except Exception as e:
        st.session_state.auto_summary = f"Could not start: {e}"
        return
    # Fixed-seed source priority: target metadata → backend's current seed → locked random.
    seed = get_target_seed()
    src = "target image metadata"
    if seed is None:
        seed = backend.current_seed() if hasattr(backend, "current_seed") else None
        src = "InvokeAI's current seed"
    if seed is None:
        seed = random.randint(0, 2**31 - 1)
        src = "a locked random seed"
    st.session_state.fixed_seed = seed
    st.session_state.fixed_seed_src = src
    strategy = st.session_state.get("refine_seed_strategy", "fixed_then_random")
    st.session_state.auto_phase = "random" if strategy == "random" else "fixed"
    st.session_state.auto_running = True
    st.session_state.auto_iter = 0
    st.session_state.auto_stop = False
    st.session_state.plateau_count = 0
    st.session_state.auto_summary = ""
    st.rerun()

def run_auto_step():
    max_iters = int(st.session_state.get("refine_max_iters", 5))
    plateau_n = int(st.session_state.get("refine_plateau_n", 2))
    if st.session_state.auto_stop:
        stop_auto("Stopped by user."); st.rerun(); return
    if st.session_state.auto_iter >= max_iters:
        stop_auto(f"Reached the max of {max_iters} iterations."); st.rerun(); return
    if refine_done_flag():
        stop_auto("The model judged the prompt is as good as it will get."); st.rerun(); return
    if st.session_state.plateau_count >= plateau_n:
        strategy = st.session_state.get("refine_seed_strategy", "fixed_then_random")
        if strategy == "fixed_then_random" and st.session_state.auto_phase == "fixed":
            # Escalate: prompt-only refinement stalled → explore compositions with random seeds.
            st.session_state.auto_phase = "random"
            st.session_state.plateau_count = 0
            st.session_state.auto_summary = "Prompt-only refinement plateaued — now randomizing the seed to explore compositions."
        else:
            stop_auto(f"No improvement for {plateau_n} rounds — stopping."); st.rerun(); return

    backend = get_or_create_backend(st.session_state.get("refine_backend", "invokeai"))
    prompt = current_best_prompt()
    targets = get_starting_image_paths()
    if not targets:
        stop_auto("Starting image was removed — stopping."); st.rerun(); return
    prev = last_result_path()

    strategy = st.session_state.get("refine_seed_strategy", "fixed_then_random")
    use_seed = None if (strategy == "random" or st.session_state.auto_phase == "random") else st.session_state.fixed_seed
    phase_label = "random seed" if use_seed is None else f"fixed seed {use_seed}"
    try:
        with st.status(f"Auto-refine iteration {st.session_state.auto_iter + 1}/{max_iters} ({phase_label})…", expanded=True) as status:
            def prog(msg):
                status.update(label=msg)
            res = backend.generate(prompt, params={"seed": use_seed}, progress=prog)
            prog("Reviewing result against the target…")
            verdict = run_vision_review(targets, prev, res.image_path, prompt)
            status.update(label=f"Iteration {st.session_state.auto_iter + 1}: {verdict['decision']} (seed {res.seed})", state="complete")
    except Exception as e:
        stop_auto(f"Generation failed: {e}"); st.rerun(); return

    record_refine_step(res.image_path, res.image_path.name, prompt, verdict, f"auto #{st.session_state.auto_iter + 1}", seed=res.seed)
    update_after_verdict(verdict, prompt)
    st.session_state.auto_iter += 1
    st.rerun()

def generate_prompt_in_backend(prompt):
    """Generate `prompt` via the selected image backend and show the result.

    A plain 'test this prompt' action — it does NOT run the compare/refine
    review. Drop the result into Resulting Images if you want to refine it.
    """
    if not prompt or not prompt.strip():
        st.warning("This message has no prompt text to generate."); return False
    backend = get_or_create_backend(st.session_state.get("refine_backend", "invokeai"))
    try:
        backend.prepare()
        with st.spinner(f"Generating in {backend.display_name}…"):
            res = backend.generate(prompt, params={"seed": None})
    except Exception as e:
        st.error(f"{backend.display_name} generation failed: {e}"); return False

    st.session_state.messages.append({
        "role": "assistant", "content": "",
        "display_content": f"🎨 **Generated in {backend.display_name}** (seed {res.seed})",
        "images": [{"path": str(res.image_path), "name": res.image_path.name}],
        "id": str(uuid.uuid4()), "model": backend.id,
    })
    auto_save_chat()
    return True

def render_refine_section(current_provider):
    st.divider()
    st.subheader("Resulting Images — compare & refine")

    if current_provider == "MiniCPM":
        st.info("Compare & refine needs a provider that accepts more than one image at a time. "
                "MiniCPM only reads the first — switch to Unsloth, LM Studio, Koboldcpp, Ollama, or Google.")
        return
    if not st.session_state.uploaded_files:
        st.caption("Add a Starting Image above, generate a prompt with **Analyze Image(s)**, "
                   "then drop your generated result here to start refining.")
        return

    # --- Manual drop: dropping a result immediately triggers a review ---
    st.markdown("**Drop a generated result to refine the prompt** (fires immediately):")
    result_file = st.file_uploader(
        "⬇ Drop generated result here",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=False,
        key=st.session_state.result_uploader_key,
        label_visibility="collapsed",
        disabled=st.session_state.auto_running,
    )
    if result_file is not None and not st.session_state.auto_running:
        sig = f"{result_file.name}:{result_file.size}"
        if sig != st.session_state.last_result_sig:
            # Record the signature FIRST so a persistent failure can't auto-retry
            # every rerun; a Retry button below handles deliberate re-runs.
            st.session_state.last_result_sig = sig
            path, name = save_uploaded_file(result_file)
            st.session_state.refine_retry = {"path": str(path), "name": name}
            try:
                do_refine_from_result(path, name, source="manual drop")
                st.session_state.refine_retry = None
                st.session_state.refine_error = None
            except Exception as e:
                st.session_state.refine_error = str(e)
            st.rerun()

    if st.session_state.get("refine_error"):
        st.error(f"Refine failed: {st.session_state.refine_error}")
        retry = st.session_state.get("refine_retry")
        if retry and st.button("🔁 Retry review", disabled=st.session_state.auto_running):
            try:
                do_refine_from_result(Path(retry["path"]), retry["name"], source="manual drop (retry)")
                st.session_state.refine_error = None
                st.session_state.refine_retry = None
            except Exception as e:
                st.session_state.refine_error = str(e)
            st.rerun()

    # --- Auto-refine loop ---
    with st.expander("🤖 Auto-refine loop (generate → review → repeat)", expanded=st.session_state.auto_running):
        names = image_backends.backend_display_names()
        st.selectbox("Image-generation backend", options=list(names.keys()),
                     format_func=lambda k: names[k], key="refine_backend",
                     disabled=st.session_state.auto_running)
        backend = get_or_create_backend(st.session_state.get("refine_backend", "invokeai"))
        stt = backend.status()
        st.caption(("✅ " if stt.available else "❌ ") + stt.detail)

        c1, c2 = st.columns(2)
        c1.number_input("Max iterations", min_value=1, max_value=25, value=5,
                        key="refine_max_iters", disabled=st.session_state.auto_running)
        c2.number_input("Stop after N non-improving rounds", min_value=1, max_value=10, value=2,
                        key="refine_plateau_n", disabled=st.session_state.auto_running)

        seed_labels = {
            "fixed_then_random": "Fixed, then randomize on plateau (recommended)",
            "fixed": "Fixed seed only",
            "random": "Random seed each cycle",
        }
        st.selectbox("Seed strategy", options=list(seed_labels.keys()),
                     format_func=lambda k: seed_labels[k], key="refine_seed_strategy",
                     disabled=st.session_state.auto_running)
        st.caption("Fixed seed holds the composition so only the prompt varies. Its value comes "
                   "from the target image's metadata if present, else InvokeAI's current seed. "
                   "'Fixed then randomize' explores new seeds once wording stops helping.")

        if not st.session_state.auto_running:
            if backend.id == "invokeai":
                if st.button("📸 Capture current InvokeAI setup"):
                    try:
                        st.success("Captured: " + backend.capture_template())
                    except Exception as e:
                        st.error(str(e))
                if backend.describe_setup():
                    st.caption("Setup: " + backend.describe_setup())
            has_prompt = bool(current_best_prompt())
            if st.button("▶ Start auto-refine", disabled=not stt.available or not has_prompt, type="primary"):
                start_auto_loop()
            if not has_prompt:
                st.caption("Generate an initial prompt first (Analyze the starting image), then start.")
        else:
            if st.button("⏹ Stop", type="primary"):
                st.session_state.auto_stop = True
                st.rerun()
            phase = st.session_state.auto_phase
            seed_txt = f"random seed" if phase == "random" else f"fixed seed {st.session_state.get('fixed_seed')}"
            src = st.session_state.get("fixed_seed_src", "")
            st.caption(f"Running… iteration {st.session_state.auto_iter}/{int(st.session_state.get('refine_max_iters', 5))} "
                       f"· {seed_txt}" + (f" (from {src})" if phase != 'random' and src else "") + " "
                       f"· plateau {st.session_state.plateau_count}/{int(st.session_state.get('refine_plateau_n', 2))} "
                       "· (Stop takes effect after the current image finishes)")

        if st.session_state.auto_summary:
            st.info(st.session_state.auto_summary)

    # --- Progress gallery ---
    entries = refine_entries()
    if entries:
        targets = get_starting_image_paths()
        st.markdown(f"**Refinement progress — {len(entries)} step(s):**")
        for i, e in enumerate(entries, 1):
            with st.container(border=True):
                gc1, gc2 = st.columns(2)
                with gc1:
                    st.caption("🎯 Target")
                    if targets:
                        st.image(str(targets[0]), width=160)
                with gc2:
                    badge = {"IMPROVE": "🟢 IMPROVE", "REVERT": "🟠 REVERT", "DONE": "✅ DONE"}.get(e["decision"], e["decision"])
                    seed_note = f" · seed {e['seed']}" if e.get("seed") is not None else ""
                    st.caption(f"Result v{i} · {badge}{seed_note}")
                    if Path(e["result_path"]).exists():
                        st.image(e["result_path"], width=160)
                st.caption(e["assessment"])
                cols = st.columns([1, 1, 1])
                with cols[0].popover(f"Prompt v{i}", use_container_width=True):
                    st.code(e["next_prompt"], language=None)
                with cols[1]:
                    copy_button(e["next_prompt"], key=f"copy_refine_{i}")
                with cols[2]:
                    if st.button("🎨 Generate", key=f"gen_refine_{i}", use_container_width=True,
                                 disabled=st.session_state.auto_running):
                        if generate_prompt_in_backend(e["next_prompt"]):
                            st.rerun()

def remove_uploaded_image(idx):
    if 0 <= idx < len(st.session_state.uploaded_files):
        del st.session_state.uploaded_files[idx]
        st.rerun()

def remove_uploaded_video(idx):
    if 0 <= idx < len(st.session_state.uploaded_videos):
        del st.session_state.uploaded_videos[idx]
        st.rerun()

def copy_button(text, key):
    """Render a small copy-to-clipboard icon button (works via browser clipboard, localhost is a secure context)."""
    payload = json.dumps(text or "")
    components.html(f"""
    <div style="display:flex;justify-content:center;">
      <button id="cb_{key}" title="Copy to clipboard"
        style="background:transparent;border:none;cursor:pointer;padding:4px;color:#888;display:flex;align-items:center;">
        <svg id="ic_{key}" width="18" height="18" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
      </button>
    </div>
    <script>
      const btn_{key} = document.getElementById("cb_{key}");
      btn_{key}.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText({payload});
        }} catch (e) {{
          const ta = document.createElement("textarea");
          ta.value = {payload}; document.body.appendChild(ta); ta.select();
          document.execCommand("copy"); ta.remove();
        }}
        const ic = document.getElementById("ic_{key}");
        ic.innerHTML = '<polyline points="20 6 9 17 4 12"></polyline>';
        btn_{key}.style.color = "#2ecc71";
        setTimeout(() => {{
          ic.innerHTML = '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>'
            + '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>';
          btn_{key}.style.color = "#888";
        }}, 1200);
      }});
    </script>
    """, height=32)


def remove_message(idx):
    if 0 <= idx < len(st.session_state.messages):
        del st.session_state.messages[idx]
        st.rerun()

def regenerate_message(idx, container=None):
    # Only allow regeneration for assistant messages
    if 0 <= idx < len(st.session_state.messages):
        msg = st.session_state.messages[idx]
        if msg.get('role') != 'assistant':
            st.warning('Only assistant messages can be regenerated.')
            return
        # Find the user message before this assistant message
        user_idx = idx - 1
        while user_idx >= 0 and st.session_state.messages[user_idx].get('role') != 'user':
            user_idx -= 1
        if user_idx < 0:
            st.warning('No user message found to regenerate from.')
            return
        user_msg = st.session_state.messages[user_idx]
        # Prepare context up to and including the user message
        context_msgs = []
        for m in st.session_state.messages[:user_idx+1]:
            if m.get('role') == 'system':
                continue
            context_msgs.append({'role': m['role'], 'content': m['content']})
        # Add system prompt
        api_messages = [{'role': 'system', 'content': st.session_state.current_system_prompt}] + context_msgs
        # Get images from user message if any
        image_info = user_msg.get('images', [])
        image_paths = [Path(info['path']) for info in image_info]
        # Call the LLM for each selected model (regenerate only for the model of this message)
        model = msg.get('model', st.session_state.config['providers'][st.session_state.config['api_provider']]['selected_models'][0])
        # Prepare MiniCPM config if needed
        minicpm_config = None
        if st.session_state.config['api_provider'] == 'MiniCPM':
            minicpm_config = st.session_state.config['providers'][st.session_state.config['api_provider']]
        
        api_client = APIClient(
            provider=st.session_state.config['api_provider'],
            base_url=st.session_state.config['providers'][st.session_state.config['api_provider']]['api_base_url'] if st.session_state.config['api_provider'] not in ['Google', 'MiniCPM'] else None,
            google_api_key=st.session_state.config.get('google_api_key') if st.session_state.config['api_provider'] == 'Google' else None,
            unload_after_response=st.session_state.config['providers'][st.session_state.config['api_provider']].get("unload_after_response", False) if st.session_state.config['api_provider'] in ['LM Studio', 'MiniCPM', 'Unsloth'] else False,
            minicpm_config=minicpm_config,
            api_key=st.session_state.config['providers'][st.session_state.config['api_provider']].get('api_key') if st.session_state.config['api_provider'] == 'Unsloth' else None
        )
        target = container if container is not None else st
        message_placeholder = target.empty()
        prefix = f"**Response from `{model}`:**\n\n"
        message_placeholder.markdown(prefix + "▌")
        full_response = ""
        try:
            stream_generator = api_client.generate_chat_response(model=model, messages=copy.deepcopy(api_messages), images=image_paths)
            for chunk in stream_generator:
                full_response += chunk
                # Filter out thinking tags before displaying
                cleaned_response = remove_thinking_tags(full_response)
                message_placeholder.markdown(prefix + cleaned_response + "▌")
            # Final cleanup before saving
            full_response = remove_thinking_tags(full_response)
            message_placeholder.markdown(prefix + full_response)
        except Exception as e:
            st.error(f"An error occurred with model {model}: {e}"); full_response = f"Error: {e}"
            message_placeholder.markdown(prefix + full_response)
        display_response = prefix + full_response
        # Insert a new assistant message right after the current one
        new_message = {
            'role': 'assistant',
            'content': full_response,
            'display_content': display_response,
            'model': model,
            'id': str(uuid.uuid4())
        }
        st.session_state.messages.insert(idx + 1, new_message)
        auto_save_chat()
        st.rerun()

# --- Sidebar ---

with st.sidebar:
    st.header("💬 Conversations")
    if st.button("➕ New Chat", use_container_width=True, on_click=start_new_chat): st.rerun()
    saved_chats = cm.list_conversations()
    chat_options = {f.name: f.name.replace(".json", "").replace("_", " ") for f in saved_chats}
    options_with_placeholder = {"": "Select a chat..."}; options_with_placeholder.update(chat_options)
    current_selection_key = st.session_state.chat_id if st.session_state.chat_id in chat_options else ""
    st.selectbox("Load Chat", options=list(options_with_placeholder.keys()), format_func=lambda x: options_with_placeholder[x], index=list(options_with_placeholder.keys()).index(current_selection_key), on_change=load_chat_callback, key="selected_chat")
    if st.session_state.chat_id:
        with st.expander("Manage Current Chat"):
            new_chat_name = st.text_input("Rename chat:", value=chat_options.get(st.session_state.chat_id, ""))
            if st.button("Rename", use_container_width=True):
                if new_chat_name and new_chat_name != chat_options.get(st.session_state.chat_id, ""):
                    new_filename = new_chat_name.replace(" ", "_") + ".json"
                    if cm.rename_conversation(st.session_state.chat_id, new_filename): st.session_state.chat_id = new_filename; st.toast("Chat renamed!", icon="✏️"); st.rerun()
                    else: st.error("A chat with this name already exists.")
            if st.button("Delete Chat", type="primary", use_container_width=True):
                cm.delete_conversation(st.session_state.chat_id); start_new_chat(); st.toast("Chat deleted!", icon="🗑️"); st.rerun()
    st.divider()
    st.header("⚙️ Configuration")
    api_providers = ["Ollama", "LM Studio", "Koboldcpp", "Unsloth", "Google", "MiniCPM"]
    current_provider = st.session_state.config.get("api_provider", "Ollama")
    st.session_state.config["api_provider"] = st.radio(
        "API Provider",
        api_providers,
        index=api_providers.index(current_provider) if current_provider in api_providers else 0,
        key="api_provider_selector",
        disabled=st.session_state.generating,
        on_change=lambda: cm.save_config(st.session_state.config) # Save config on provider change
    )

    # Get current provider's specific config
    current_provider_name = st.session_state.config["api_provider"]
    provider_config = st.session_state.config["providers"].setdefault(current_provider_name, {"api_base_url": "", "selected_models": []})

    if current_provider_name == "Google":
        st.session_state.config["google_api_key"] = st.text_input(
            "Google API Key",
            value=st.session_state.config.get("google_api_key", ""),
            key="google_api_key_input",
            type="password",
            disabled=st.session_state.generating,
            on_change=lambda: cm.save_config(st.session_state.config)
        )
    elif current_provider_name == "MiniCPM":
        st.subheader("MiniCPM Configuration")
        
        # Device selection
        device_options = ["auto", "cuda", "cpu"]
        current_device = provider_config.get("device", "auto")
        provider_config["device"] = st.selectbox(
            "Device",
            device_options,
            index=device_options.index(current_device) if current_device in device_options else 0,
            key="minicpm_device_selector",
            disabled=st.session_state.generating,
            on_change=lambda: cm.save_config(st.session_state.config)
        )
        
        # Video Analysis Parameters
        st.subheader("Video Analysis Parameters")
        
        provider_config["max_num_frames"] = st.number_input(
            "MAX_NUM_FRAMES (Total frames to analyze)",
            min_value=1,
            max_value=1000,
            value=provider_config.get("max_num_frames", 180),
            key="minicpm_max_frames",
            disabled=st.session_state.generating,
            help="Controls the total number of frames to analyze from the video",
            on_change=lambda: cm.save_config(st.session_state.config)
        )
        
        provider_config["max_num_packing"] = st.number_input(
            "MAX_NUM_PACKING (Frame grouping)",
            min_value=1,
            max_value=6,
            value=provider_config.get("max_num_packing", 3),
            key="minicpm_max_packing",
            disabled=st.session_state.generating,
            help="Determines how frames are grouped together for processing (valid range: 1-6)",
            on_change=lambda: cm.save_config(st.session_state.config)
        )
        
        provider_config["default_fps"] = st.number_input(
            "Default FPS (Leave 0 for auto-calculation)",
            min_value=0.0,
            max_value=60.0,
            value=float(provider_config.get("default_fps", 3.0)),
            step=0.1,
            key="minicpm_default_fps",
            disabled=st.session_state.generating,
            help="FPS for video sampling. Set to 0 to auto-calculate based on video duration and frame parameters",
            on_change=lambda: cm.save_config(st.session_state.config)
        )
        
        # Additional options
        provider_config["enable_thinking"] = st.checkbox(
            "Enable thinking mode",
            value=provider_config.get("enable_thinking", False),
            key="minicpm_enable_thinking",
            disabled=st.session_state.generating,
            help="Enable thinking mode for more detailed analysis",
            on_change=lambda: cm.save_config(st.session_state.config)
        )
        
        provider_config["auto_unload"] = st.checkbox(
            "Auto-unload model after response",
            value=provider_config.get("auto_unload", False),
            key="minicpm_auto_unload",
            disabled=st.session_state.generating,
            help="Automatically unload the model from memory after each response to save GPU memory",
            on_change=lambda: cm.save_config(st.session_state.config)
        )
    else:
        default_urls = {
            "Ollama": "http://localhost:11434",
            "LM Studio": "http://localhost:1234",
            "Koboldcpp": "http://localhost:5001",
            "Unsloth": "http://localhost:8889"
        }
        # Use the saved URL for the current provider, or its default if not set.
        # `or` (not .get default) so an empty saved string also falls back to the default.
        current_api_base_url = provider_config.get("api_base_url") or default_urls.get(current_provider_name, "")
        provider_config["api_base_url"] = st.text_input(
            "API Base URL",
            value=current_api_base_url,
            key=f"api_base_url_input_{current_provider_name}", # Unique key for each provider
            disabled=st.session_state.generating,
            on_change=lambda: cm.save_config(st.session_state.config)
        )
        if current_provider_name == "Unsloth":
            provider_config["api_key"] = st.text_input(
                "API Key",
                value=provider_config.get("api_key", ""),
                type="password",
                help="Unsloth Studio API key — mint one in Studio under Settings > API. Sent as the OpenAI Bearer token.",
                key=f"api_key_input_{current_provider_name}",
                disabled=st.session_state.generating,
                on_change=lambda: cm.save_config(st.session_state.config)
            )
        if current_provider_name in ("LM Studio", "Unsloth"):
            provider_config["unload_after_response"] = st.checkbox(
                "Unload model after response",
                value=provider_config.get("unload_after_response", False),
                key=f"unload_after_response_checkbox_{current_provider_name}",
                disabled=st.session_state.generating,
                on_change=lambda: cm.save_config(st.session_state.config)
            )
        if current_provider_name == "Ollama":
            current_keep_alive = provider_config.get("keep_alive", -1) # Default to -1 (server default)
            provider_config["keep_alive"] = st.number_input(
                "Keep Alive (seconds, -1 for server default, 0 for no cache)",
                min_value=-1,
                value=current_keep_alive,
                key=f"ollama_keep_alive_{current_provider_name}",
                disabled=st.session_state.generating,
                on_change=lambda: cm.save_config(st.session_state.config)
            )
    
    # Instantiate APIClient with current provider's settings
    minicpm_config = None
    if current_provider_name == "MiniCPM":
        minicpm_config = provider_config
    
    api_client = APIClient(
        provider=current_provider_name,
        base_url=provider_config.get("api_base_url") if current_provider_name not in ["Google", "MiniCPM"] else None,
        google_api_key=st.session_state.config.get("google_api_key") if current_provider_name == "Google" else None,
        ollama_keep_alive=provider_config.get("keep_alive") if current_provider_name == "Ollama" else None, # Pass keep_alive
        unload_after_response=provider_config.get("unload_after_response", False) if current_provider_name in ("LM Studio", "Unsloth") else provider_config.get("auto_unload", False) if current_provider_name == "MiniCPM" else False,
        minicpm_config=minicpm_config,
        api_key=provider_config.get("api_key") if current_provider_name == "Unsloth" else None
    )

    with st.spinner("Fetching available models..."):
        available_models = api_client.get_available_models()

    if not available_models:
        st.error("Could not connect or no models found.")
    else:
        # Use the saved selected models for the current provider
        saved_selection = provider_config.get("selected_models", [])
        valid_selection = [model for model in saved_selection if model in available_models]
        
        # Update the selected_models for the current provider
        provider_config["selected_models"] = st.multiselect(
            "Select Model(s)",
            options=available_models,
            default=valid_selection,
            key=f"selected_models_multiselect_{current_provider_name}", # Unique key
            disabled=st.session_state.generating,
            on_change=lambda: cm.save_config(st.session_state.config)
        )

    st.subheader("Model Management")
    is_ollama = current_provider_name == "Ollama"
    
    
    # --- System Prompt Management ---
    st.subheader("System Prompt")

    with st.expander("System Prompt Builder"):
        st.header("System Prompt Builder")

        caption_type = st.selectbox(
            "Caption Type",
            list(CAPTION_TYPE_MAP.keys()),
            key="modal_caption_type"
        )

        caption_length = st.selectbox(
            "Caption Length",
            ["any", "very short", "short", "medium-length", "long", "very long"] + [str(i) for i in range(20, 261, 10)],
            key="modal_caption_length"
        )

        st.markdown("**Extra Options**")
        extra_options_keys = EXTRA_OPTIONS_KEYS

        extra_options_state = {}
        for i, option in enumerate(extra_options_keys):
            extra_options_state[option] = st.checkbox(option, key=f"modal_extra_option_{i}")

        name_input = ""
        if extra_options_state[NAME_OPTION]:
            name_input = st.text_input("Person / Character Name", key="modal_name_input")

        def build_prompt(caption_type: str, caption_length: str | int, extra_options: dict, name_input: str) -> str:
            if caption_length == "any":
                map_idx = 0
            elif isinstance(caption_length, str) and caption_length.isdigit():
                map_idx = 1
            else:
                map_idx = 2
            
            prompt = CAPTION_TYPE_MAP[caption_type][map_idx]

            selected_options = [option for option, checked in extra_options.items() if checked]
            if selected_options:
                prompt += " " + " ".join(selected_options)
            
            return prompt.format(
                name=name_input or "{NAME}",
                length=caption_length,
                word_count=caption_length,
            )

        if st.button("Generate and Apply Prompt", use_container_width=True):
            built_prompt = build_prompt(caption_type, caption_length, extra_options_state, name_input)
            st.session_state.current_system_prompt = built_prompt
            # Push it into the text-area's own keyed state too, otherwise the
            # widget keeps showing its previous value (Streamlit uses the keyed
            # state over the `value=` arg once the widget has been rendered).
            st.session_state["system_prompt_text_area"] = built_prompt
            # Remember this builder state so it survives an app restart.
            st.session_state.builder_configs["__last__"] = _current_builder_config()
            cm.save_builder_configs(st.session_state.builder_configs)
            st.rerun()

    prompt_names = list(st.session_state.system_prompts.keys())
    try:
        current_prompt_index = prompt_names.index(st.session_state.current_system_prompt_name) + 1
    except (ValueError, AttributeError):
        current_prompt_index = 0

    def on_prompt_change():
        selected_name = st.session_state.prompt_selector
        if selected_name != "New Custom Prompt":
            st.session_state.current_system_prompt_name = selected_name
            st.session_state.current_system_prompt = st.session_state.system_prompts[selected_name]
            st.session_state["system_prompt_text_area"] = st.session_state.system_prompts[selected_name]
            st.session_state.config['last_system_prompt_name'] = selected_name
            # Repopulate the builder checkboxes from this prompt's saved config
            # (runs in a callback, before the builder widgets re-instantiate).
            saved_cfg = st.session_state.builder_configs.get(selected_name)
            if saved_cfg:
                apply_builder_config(saved_cfg)
        else:
            st.session_state.current_system_prompt_name = ""

    st.selectbox("Choose or create a prompt", options=["New Custom Prompt"] + prompt_names, index=current_prompt_index, on_change=on_prompt_change, key="prompt_selector", disabled=st.session_state.generating)
    st.text_area("System Prompt Content", height=200, key="system_prompt_text_area", disabled=st.session_state.generating)
    st.session_state.current_system_prompt = st.session_state["system_prompt_text_area"]
    prompt_save_name = st.text_input("Enter name to save prompt:", value=st.session_state.get("current_system_prompt_name", ""), disabled=st.session_state.generating)
    if st.button("Save System Prompt", disabled=st.session_state.generating):
        if prompt_save_name:
            st.session_state.system_prompts[prompt_save_name] = st.session_state.current_system_prompt
            cm.save_system_prompts(st.session_state.system_prompts)
            # Save the builder checkbox state under this name so it can be
            # reloaded and tweaked later, and remember it as the last-used state.
            builder_cfg = _current_builder_config()
            st.session_state.builder_configs[prompt_save_name] = builder_cfg
            st.session_state.builder_configs["__last__"] = builder_cfg
            cm.save_builder_configs(st.session_state.builder_configs)
            st.session_state.current_system_prompt_name = prompt_save_name
            st.session_state.config['last_system_prompt_name'] = prompt_save_name
            st.toast(f"Prompt '{prompt_save_name}' saved!", icon="✅"); st.rerun()
        else: st.warning("Please enter a name for the prompt before saving.")
    cm.save_config(st.session_state.config)
    # --- Export Conversation ---
    st.subheader("Export Conversation")
    if st.session_state.messages:
        col1, col2 = st.columns(2)
        chat_name = st.session_state.chat_id.replace(".json", "") if st.session_state.chat_id else f"conversation_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        txt_data = "".join(f"--- {msg['role'].upper()} ---\n{msg.get('display_content', '')}\n\n" for msg in st.session_state.messages)
        col1.download_button("to .txt", txt_data, f"{chat_name}.txt", "text/plain")
        json_data = json.dumps(st.session_state.messages, indent=2)
        col2.download_button("to .json", json_data, f"{chat_name}.json", "application/json")
    st.sidebar.divider(); st.sidebar.markdown("- [My Website](https://eng.webphotogallery.store/i2p)\n- [GitHub Project Page](https://github.com/rorsaeed/image-to-prompt)")

# --- Custom CSS for transparent X buttons ---
st.markdown(
    """
    <style>
    button[data-testid=\"baseButton\"]:has(div:contains('×')),
    button[data-testid=\"baseButton\"]:has(span:contains('×')) {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #222 !important;
        font-size: 1em;
        padding: 0.05em 0.3em;
        margin: 0;
        transition: color 0.2s;
    }
    button[data-testid=\"baseButton\"]:has(div:contains('×')):hover, 
    button[data-testid=\"baseButton\"]:has(span:contains('×')):hover {
        color: #000 !important;
        background: transparent !important;
    }
    
    /* Global video size constraints - apply to all videos */
    [data-testid="stVideo"] {
        max-width: 250px !important;
        width: auto !important;
    }
    
    [data-testid="stVideo"] > div {
        max-width: 250px !important;
        width: auto !important;
    }
    
    [data-testid="stVideo"] video {
        max-width: 250px !important;
        max-height: 200px !important;
        width: auto !important;
        height: auto !important;
        object-fit: contain !important;
    }
    
    /* Video thumbnail styling with higher specificity */
    .video-thumbnail [data-testid="stVideo"],
    .video-thumbnail [data-testid="stVideo"] > div,
    .video-thumbnail [data-testid="stVideo"] > div > div {
        max-width: 250px !important;
        width: auto !important;
    }
    
    .video-thumbnail [data-testid="stVideo"] > div > div > video,
    .video-thumbnail [data-testid="stVideo"] video {
        max-width: 250px !important;
        max-height: 200px !important;
        width: auto !important;
        height: auto !important;
        object-fit: contain !important;
    }
    
    .video-thumbnail-small [data-testid="stVideo"],
    .video-thumbnail-small [data-testid="stVideo"] > div,
    .video-thumbnail-small [data-testid="stVideo"] > div > div {
        max-width: 250px !important;
        width: auto !important;
    }
    
    .video-thumbnail-small [data-testid="stVideo"] > div > div > video,
    .video-thumbnail-small [data-testid="stVideo"] video {
        max-width: 250px !important;
        max-height: 150px !important;
        width: auto !important;
        height: auto !important;
        object-fit: contain !important;
    }
    
    /* Metadata display styling - Using Streamlit default colors */
    .metadata-section {
        background-color: transparent;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        border-left: 4px solid #007bff;
        border: 1px solid rgba(49, 51, 63, 0.2);
    }
    
    .metadata-title {
        font-weight: bold;
        margin-bottom: 8px;
        font-size: 14px;
    }
    
    .metadata-item {
        margin: 4px 0;
        font-size: 12px;
        line-height: 1.4;
    }
    
    .metadata-key {
        font-weight: 600;
        opacity: 0.7;
    }
    
    .metadata-value {
        word-break: break-word;
    }
    
    .ai-metadata {
        border-left-color: #28a745;
        background-color: rgba(40, 167, 69, 0.05);
    }
    
    .technical-metadata {
        border-left-color: #ffc107;
        background-color: rgba(255, 193, 7, 0.05);
    }
    
    /* Light theme variables (default) */
    :root {
        --background-color: #ffffff;
        --section-background-color: #f9fafb;
        --border-color: #9ca3af;
        --text-color: #111827;
        --secondary-text-color: #1f2937;
        --ai-background-color: #ecfdf5;
        --technical-background-color: #fef3c7;
        --file-background-color: #ede9fe;
    }
    
    /* Dark theme variables - Multiple detection methods */
    @media (prefers-color-scheme: dark) {
        :root {
            --background-color: #2d3748;
            --section-background-color: #2d3748;
            --border-color: #4a5568;
            --text-color: #e2e8f0;
            --secondary-text-color: #a0aec0;
            --ai-background-color: #1a2f1a;
            --technical-background-color: #2d2a1a;
            --file-background-color: #2d1b3d;
        }
    }
    
    /* Streamlit dark theme detection - body class */
    body[data-theme="dark"],
    .stApp[data-theme="dark"],
    [data-theme="dark"] {
        --background-color: #2d3748;
        --section-background-color: #2d3748;
        --border-color: #4a5568;
        --text-color: #e2e8f0;
        --secondary-text-color: #a0aec0;
        --ai-background-color: #1a2f1a;
        --technical-background-color: #2d2a1a;
        --file-background-color: #2d1b3d;
    }
    
    /* Additional Streamlit dark theme selectors */
    .stApp:has([data-testid="stSidebar"][data-theme="dark"]),
    html:has(.stApp[data-theme="dark"]) {
        --background-color: #2d3748;
        --section-background-color: #2d3748;
        --border-color: #4a5568;
        --text-color: #e2e8f0;
        --secondary-text-color: #a0aec0;
        --ai-background-color: #1a2f1a;
        --technical-background-color: #2d2a1a;
        --file-background-color: #2d1b3d;
    }
    
    .file-metadata {
        border-left-color: #6f42c1;
        background-color: rgba(111, 66, 193, 0.05);
    }
    

    </style>
    
    <script>
    // Enhanced theme detection for Streamlit
    function detectAndApplyTheme() {
        const stApp = document.querySelector('.stApp');
        const sidebar = document.querySelector('[data-testid="stSidebar"]');
        const body = document.body;
        const html = document.documentElement;
        
        // Check multiple sources for theme
        const isDark = 
            window.matchMedia('(prefers-color-scheme: dark)').matches ||
            (stApp && stApp.getAttribute('data-theme') === 'dark') ||
            (sidebar && sidebar.getAttribute('data-theme') === 'dark') ||
            (body && body.getAttribute('data-theme') === 'dark') ||
            (html && html.getAttribute('data-theme') === 'dark');
        
        // Apply theme to multiple elements
        const themeValue = isDark ? 'dark' : 'light';
        
        if (stApp) stApp.setAttribute('data-theme', themeValue);
        if (body) body.setAttribute('data-theme', themeValue);
        if (html) html.setAttribute('data-theme', themeValue);
        
        console.log('Theme detected and applied:', themeValue);
    }
    
    // Run theme detection
    detectAndApplyTheme();
    
    // Watch for theme changes
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', detectAndApplyTheme);
    }
    
    // Watch for DOM changes (Streamlit updates)
    const observer = new MutationObserver(detectAndApplyTheme);
    observer.observe(document.body, { 
        attributes: true, 
        attributeFilter: ['data-theme', 'class'],
        subtree: true 
    });
    
    // Periodic check as fallback
    setInterval(detectAndApplyTheme, 1000);
    </script>
    """,
    unsafe_allow_html=True
)

# --- Theme Detection and Application ---
# Add additional theme detection using Streamlit's component system
st.markdown("""
<script>
// Force theme detection on page load
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        detectAndApplyTheme();
    }, 100);
});

// Additional theme detection for Streamlit updates
window.addEventListener('load', function() {
    setTimeout(function() {
        detectAndApplyTheme();
    }, 500);
});
</script>
""", unsafe_allow_html=True)

# --- Main Application Area ---
st.title("🖼️ Image-to-Prompt AI Assistant")
st.warning("**Important:** For local models, ensure **LM Studio** or **Ollama** is running with the API server enabled and a vision model loaded. For Google, ensure you have entered a valid API key.")

tab1, tab2, tab3 = st.tabs(["Chat", "Bulk Analysis", "Recommended Models"])

with tab1:
    # Create a list of containers for each message so we can update them in-place
    message_containers = []
    for idx, message in enumerate(st.session_state.messages):
        container = st.container()
        message_containers.append(container)
        with container:
            col_msg, col_copy, col_btn, col_regen = st.columns([8, 1, 1, 1])
            with col_msg:
                if "display_content" in message:
                    st.markdown(message["display_content"])
                if "images" in message:
                    img_cols = st.columns(len(message["images"]))
                    for j, image_info in enumerate(message["images"]):
                        with img_cols[j]:
                            img_path = Path(image_info["path"])
                            if img_path.exists():
                                st.image(str(img_path), width=150)
                                with st.popover("View Full Size", use_container_width=True):
                                    st.image(str(img_path))
                                st.caption(image_info["name"])
                if "videos" in message:
                    # Create more columns to make videos smaller
                    num_videos = len(message["videos"])
                    # Use more columns than videos to create smaller containers
                    video_cols = st.columns([1, 2, 1] if num_videos == 1 else [2] * num_videos + [1] * max(0, 3 - num_videos))
                    for j, video_info in enumerate(message["videos"]):
                        col_index = 1 if num_videos == 1 else j  # Center single video, otherwise use sequential columns
                        with video_cols[col_index]:
                            video_path = Path(video_info["path"])
                            if video_path.exists():
                                st.markdown('<div class="video-thumbnail-small">', unsafe_allow_html=True)
                                st.video(str(video_path))
                                st.markdown('</div>', unsafe_allow_html=True)
                                st.caption(video_info["name"])
                # "Generate this prompt" button under any assistant prompt
                if message.get("role") == "assistant" and (message.get("content") or "").strip():
                    _bn = image_backends.backend_display_names().get(st.session_state.get("refine_backend", "invokeai"), "InvokeAI")
                    gcols = st.columns([3, 1])
                    with gcols[1]:
                        if st.button("🎨 Generate", key=f"gen_msg_{idx}", help=f"Generate this prompt in {_bn}",
                                     use_container_width=True, disabled=st.session_state.auto_running):
                            if generate_prompt_in_backend(message["content"]):
                                st.rerun()
            with col_copy:
                if message.get('role') == 'assistant':
                    copy_button(message.get("content") or message.get("display_content", ""), key=f"copy_msg_{idx}")
            with col_btn:
                if st.button("×", key=f"remove_msg_{idx}", help="Delete this message"):
                    remove_message(idx)
            with col_regen:
                if message.get('role') == 'assistant':
                    if st.button("↻", key=f"regen_msg_{idx}", help="Regenerate this message"):
                        regenerate_message(idx, message_containers[idx])

    if st.session_state.generating:
        run_generation_logic()
    else:
        current_provider = st.session_state.config.get("api_provider", "Ollama")
        
        # Image upload section
        st.subheader("Starting Images")
        uploaded_files_from_widget = st.file_uploader(
            "Upload image(s)", 
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,  # Allow multiple images
            key=st.session_state.uploader_key
        )

        if uploaded_files_from_widget:
            # Process multiple uploaded files
            new_uploads = [save_uploaded_file(file) for file in uploaded_files_from_widget]
            st.session_state.uploaded_files = new_uploads
        elif not st.session_state.uploaded_files:
            # Initialize to empty list if nothing uploaded and no existing files
            st.session_state.uploaded_files = []
        

        
        # Video upload section (for Google and MiniCPM)
        if current_provider in ["Google", "MiniCPM"]:
            provider_text = "Google & MiniCPM" if current_provider == "MiniCPM" else "Google Only"
            st.subheader(f"Upload Videos ({provider_text})")
            uploaded_videos_from_widget = st.file_uploader(
                "Upload video(s)", 
                type=["mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "m4v"],
                accept_multiple_files=True,
                key=f"video_{st.session_state.uploader_key}"
            )

            if uploaded_videos_from_widget:
                # Process multiple uploaded video files
                new_video_uploads = [save_uploaded_video(file) for file in uploaded_videos_from_widget]
                st.session_state.uploaded_videos = new_video_uploads
            elif not st.session_state.uploaded_videos:
                # Initialize to empty list if nothing uploaded and no existing files
                st.session_state.uploaded_videos = []
        else:
            # Clear videos if not using Google or MiniCPM
            st.session_state.uploaded_videos = []
        
        # Display all uploaded images in a grid
        if st.session_state.uploaded_files:
            st.write("**Uploaded Images:**")
            num_images = len(st.session_state.uploaded_files)
            cols_per_row = min(4, num_images)  # Maximum 4 images per row
            
            # Calculate how many rows we need
            num_rows = (num_images + cols_per_row - 1) // cols_per_row
            
            # Create a grid to display images
            for row in range(num_rows):
                cols = st.columns(cols_per_row)
                for col_idx in range(cols_per_row):
                    img_idx = row * cols_per_row + col_idx
                    if img_idx < num_images:
                        file_path, original_name = st.session_state.uploaded_files[img_idx]
                        with cols[col_idx]:
                            st.image(str(file_path), caption=original_name, width=150)
                            if st.button("×", key=f"remove_img_{img_idx}", disabled=st.session_state.auto_running):
                                remove_uploaded_image(img_idx)
                            with st.popover("View Full Size", use_container_width=True):
                                st.image(str(file_path))
                            
                            # Display metadata below the image
                            display_image_metadata(file_path, original_name)

        # Resulting Images: compare & refine loop
        render_refine_section(current_provider)

        # Display all uploaded videos in a grid (for Google and MiniCPM)
        if st.session_state.uploaded_videos and current_provider in ["Google", "MiniCPM"]:
            st.write("**Uploaded Videos:**")
            num_videos = len(st.session_state.uploaded_videos)
            cols_per_row = min(4, num_videos)  # Maximum 4 videos per row for smaller thumbnails
            
            # Calculate how many rows we need
            num_rows = (num_videos + cols_per_row - 1) // cols_per_row
            
            # Create a grid to display videos with smaller columns
            for row in range(num_rows):
                # Create columns with specific widths to make videos smaller
                if cols_per_row == 1:
                    cols = st.columns([1, 2, 1])  # Center single video
                    active_cols = [1]
                elif cols_per_row == 2:
                    cols = st.columns([1, 2, 1, 2, 1])  # Two videos with spacing
                    active_cols = [1, 3]
                else:
                    cols = st.columns(cols_per_row + 2)  # Add padding columns
                    active_cols = list(range(1, cols_per_row + 1))
                
                for col_idx in range(cols_per_row):
                    vid_idx = row * cols_per_row + col_idx
                    if vid_idx < num_videos:
                        file_path, original_name = st.session_state.uploaded_videos[vid_idx]
                        with cols[active_cols[col_idx] if col_idx < len(active_cols) else col_idx]:
                            st.markdown('<div class="video-thumbnail">', unsafe_allow_html=True)
                            st.video(str(file_path))
                            st.markdown('</div>', unsafe_allow_html=True)
                            st.caption(original_name)
                            if st.button("×", key=f"remove_vid_{vid_idx}"):
                                remove_uploaded_video(vid_idx)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            has_media = bool(st.session_state.uploaded_files or st.session_state.uploaded_videos)
            if has_media:
                media_text = []
                if st.session_state.uploaded_files:
                    media_text.append("Image(s)")
                if st.session_state.uploaded_videos:
                    media_text.append("Video(s)")
                button_text = f"Analyze {' & '.join(media_text)}"
                if st.button(button_text):
                    process_and_send_message(
                        prompt_text="", 
                        uploaded_file_info=st.session_state.uploaded_files,
                        uploaded_video_info=st.session_state.uploaded_videos
                    )
        with col2:
            # Chat input
            if prompt := st.chat_input("Type your message here..."):
                process_and_send_message(
                    prompt_text=prompt,
                    uploaded_file_info=st.session_state.uploaded_files,
                    uploaded_video_info=st.session_state.uploaded_videos
                )

        # Auto-refine driver: run one generate→review step per rerun so the Stop
        # button and the progress gallery stay responsive between iterations.
        if st.session_state.auto_running:
            run_auto_step()

with tab2:
    bulk_analysis_page()

with tab3:
    st.header("Recommended Models")

    st.subheader("gemma-3-27b (24Gb+ Vram)")
    st.markdown("""
    - **LM Studio:** [Download](https://model.lmstudio.ai/download/mlabonne/gemma-3-27b-it-abliterated-GGUF)
    - **Ollama:** [gemma3](https://ollama.com/library/gemma3)
      ```bash
      ollama run gemma3:27b
      ```
    """)

    st.subheader("gemma-3-12b (8Gb+ Vram)")
    st.markdown("""
    - **LM Studio:** [Download](https://model.lmstudio.ai/download/mlabonne/gemma-3-12b-it-abliterated-GGUF)
    - **Ollama:** [gemma3](https://ollama.com/library/gemma3)
      ```bash
      ollama run gemma3:12b
      ```
    """)

    st.subheader("gemma-3-4b (4Gb+ Vram)")
    st.markdown("""
    - **LM Studio:** [Download](https://model.lmstudio.ai/download/mlabonne/gemma-3-4b-it-abliterated-GGUF)
    - **Ollama:** [gemma3](https://ollama.com/library/gemma3)
      ```bash
      ollama run gemma3
      ```
    """)

    st.subheader("llama-joycaption-beta-one-hf-llava (12Gb+ Vram)")
    st.markdown("""
    *Best for system prompt builder*
    - **LM Studio:** [Download](https://model.lmstudio.ai/download/concedo/llama-joycaption-beta-one-hf-llava-mmproj-gguf)
    - **Ollama:** [aha2025/llama-joycaption-beta-one-hf-llava](https://ollama.com/aha2025/llama-joycaption-beta-one-hf-llava)
      ```bash
      ollama run aha2025/llama-joycaption-beta-one-hf-llava
      ```
    """)

    st.subheader("Qwen2.5-VL-7B (8Gb+ Vram)")
    st.markdown("""
    - **LM Studio:** [Download](https://model.lmstudio.ai/download/Misaka27260/Qwen2.5-VL-7B-Instruct-abliterated-GGUF)
    - **Ollama:** [qwen2.5vl](https://ollama.com/library/qwen2.5vl)
      ```bash
      ollama run qwen2.5vl
      ```
    """)

# --- CSS for code block wrapping ---
st.markdown("""
    <style>
    /* Target code blocks inside Streamlit */
    .stCode > div {
        overflow-x: auto !important;
        white-space: pre-wrap !important;
        word-break: break-word !important;
    }
    .stCode code {
        white-space: pre-wrap !important;
        word-break: break-break-word !important;
    }
    </style>
    """, unsafe_allow_html=True
)

# Example: get your prompt text as before
prompt_text = st.session_state.messages[-1]["content"] if st.session_state.messages else ""

# st.markdown("**Prompt:**")
# st.code(prompt_text, language=None)  # Shows a copy button with wrapping
