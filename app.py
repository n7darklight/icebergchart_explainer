import os
import json
import re
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai
from urllib.parse import unquote
from collections import defaultdict

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'a_truly_secret_key_for_flash_messages')


# --- Configuration ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
CUSTOM_SEARCH_API_KEY = os.getenv('CUSTOM_SEARCH_API_KEY')
CUSTOM_SEARCH_ENGINE_ID = os.getenv('CUSTOM_SEARCH_ENGINE_ID')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')

# --- API URLs ---
CUSTOM_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# --- Supabase Client ---
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error initializing Supabase client: {e}")
    supabase = None

# --- Gemini Client ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def clean_html_response(text):
    """Removes markdown code fences from AI response."""
    match = re.search(r"```html\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match_json = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    if match_json:
        return match_json.group(1).strip()
    return text

# --- Main Routes ---

@app.route('/')
def index():
    """Displays the categorized list of available iceberg charts from the database."""
    if not supabase:
        return "Supabase client not initialized.", 500
    
    response = supabase.table('iceberg_charts').select('name, category').order('name').execute()
    charts = response.data if response.data else []
    
    # Group charts by category in Python
    categorized_charts = defaultdict(list)
    for chart in charts:
        category = chart.get('category') or "Uncategorized"
        categorized_charts[category].append(chart['name'])

    return render_template('index.html', categorized_charts=categorized_charts, recommended_charts=None, search_query=None)

@app.route('/search')
def search():
    """Handles topic search and recommends iceberg charts."""
    search_query = request.args.get('query', '')
    if not search_query:
        return redirect(url_for('index'))

    if not supabase:
        return "Supabase client not initialized.", 500

    try:
        response = supabase.table('iceberg_charts').select('name').order('name').execute()
        all_charts = [chart['name'] for chart in response.data] if response.data else []

        if not all_charts:
            return render_template('index.html', categorized_charts={}, recommended_charts=[], search_query=search_query)

        model = genai.GenerativeModel('gemma-3-27b-it')
        prompt = (
            f"From the following list of iceberg chart titles, which ones are most relevant to the search query '{search_query}'? "
            f"The available chart titles are: {', '.join(all_charts)}. "
            f"Return your answer as a single valid JSON array of strings, containing only the names of the most relevant charts. "
            f"For example: [\"Relevant Chart 1\", \"Relevant Chart 2\"]."
        )
        
        response = model.generate_content(prompt)
        cleaned_response = clean_html_response(response.text)
        recommended_charts = json.loads(cleaned_response)

    except Exception as e:
        print(f"Error getting recommendations: {e}")
        recommended_charts = []

    # Get all charts for background display
    response = supabase.table('iceberg_charts').select('name, category').order('name').execute()
    charts = response.data if response.data else []
    categorized_charts = defaultdict(list)
    for chart in charts:
        category = chart.get('category') or "Uncategorized"
        categorized_charts[category].append(chart['name'])


    return render_template('index.html', categorized_charts=categorized_charts, recommended_charts=recommended_charts, search_query=search_query)


@app.route('/iceberg/<chart_name>')
def iceberg_chart(chart_name):
    """Displays a specific iceberg chart by fetching its full data from Supabase."""
    if not supabase:
        return "Supabase client not initialized.", 500

    decoded_chart_name = unquote(chart_name)
    chart_response = supabase.table('iceberg_charts').select('id').eq('name', decoded_chart_name).execute()
    if not chart_response.data:
        return "Chart not found", 404
    chart_id = chart_response.data[0]['id']

    layers_response = supabase.table('iceberg_layers').select('*, iceberg_entries(*)').eq('chart_id', chart_id).order('layer_order').execute()
    if not layers_response.data:
        return render_template('iceberg.html', chart_name=decoded_chart_name, iceberg_data=[], total_entries=0)

    iceberg_data = []
    total_entries = 0
    for layer in layers_response.data:
        entries = layer.get('iceberg_entries', [])
        iceberg_data.append({
            'layer': layer['layer_name'],
            'entries': [{'text': entry['entry_text']} for entry in entries]
        })
        total_entries += len(entries)

    return render_template('iceberg.html', chart_name=decoded_chart_name, iceberg_data=iceberg_data, total_entries=total_entries)

# --- Explanation API ---

@app.route('/api/image-proxy')
def image_proxy():
    """Fetches an external image and serves it to bypass hotlinking restrictions."""
    image_url = request.args.get('url')
    if not image_url:
        return "No image URL provided", 400
    
    try:
        # Add a user-agent header to mimic a browser
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(image_url, stream=True, headers=headers, timeout=5)
        response.raise_for_status()
        
        # Stream the content back to the user
        return Response(response.iter_content(chunk_size=1024), content_type=response.headers['Content-Type'])
    except requests.exceptions.RequestException as e:
        print(f"Proxy failed for {image_url}: {e}")
        # Return a 1x1 transparent pixel on failure
        return Response(
            (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'),
            mimetype='image/png'
        )

@app.route('/api/explain', methods=['POST'])
def get_explanation():
    """API endpoint to get an explanation and related image for an iceberg entry."""
    data = request.json
    chart_name = data.get('chart_name')
    entry_text = data.get('entry_text')

    if not all([chart_name, entry_text, GEMINI_API_KEY, CUSTOM_SEARCH_API_KEY, CUSTOM_SEARCH_ENGINE_ID]):
        return jsonify({'error': 'Missing data or API key configuration.'}), 400

    search_context = "Web search failed or returned no results."
    queries_to_try = [
        f'"{entry_text}" meaning in "{chart_name}" iceberg chart',
        f'"{entry_text}" iceberg explanation',
        f'"{entry_text}" lore'
    ]
    
    for query in queries_to_try:
        try:
            text_search_params = {'key': CUSTOM_SEARCH_API_KEY, 'cx': CUSTOM_SEARCH_ENGINE_ID, 'q': query, 'num': 3}
            response = requests.get(CUSTOM_SEARCH_URL, params=text_search_params)
            response.raise_for_status()
            search_json = response.json()
            snippets = [item.get('snippet', '') for item in search_json.get('items', [])]
            if snippets:
                search_context = " ".join(snippets)
                break
        except requests.exceptions.RequestException as e:
            continue

    image_url = None
    try:
        image_search_query = f'"{entry_text}"'
        image_search_params = {'key': CUSTOM_SEARCH_API_KEY, 'cx': CUSTOM_SEARCH_ENGINE_ID, 'q': image_search_query, 'searchType': 'image', 'num': 5}
        response = requests.get(CUSTOM_SEARCH_URL, params=image_search_params)
        response.raise_for_status()
        image_results = response.json().get('items', [])
        
        for item in image_results:
            link = item.get('link')
            if not link: continue
            try:
                head_response = requests.head(link, timeout=2)
                if head_response.status_code == 200:
                    image_url = link
                    break
            except requests.exceptions.RequestException:
                continue
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch image results: {e}")

    prompt = (
        f"You are an expert explainer of internet culture. Provide a clear, concise explanation for the iceberg entry: '{entry_text}' "
        f"from the '{chart_name}' iceberg chart. Use this web search context: '{search_context}'. "
        f"Format your response in simple HTML using paragraphs (<p>) and bold tags (<b>)."
    )
    
    try:
        model = genai.GenerativeModel('gemma-3-27b-it')
        response = model.generate_content(prompt)
        explanation = clean_html_response(response.text)
        return jsonify({'explanation': explanation, 'image_url': image_url})
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return jsonify({'error': f'Failed to process AI explanation: {e}'}), 500

# --- CRUD Management Routes ---

@app.route('/manage')
def manage_charts():
    response = supabase.table('iceberg_charts').select('id, name, category').order('name').execute()
    charts = response.data if response.data else []
    return render_template('manage_charts.html', charts=charts)

@app.route('/manage/categorize', methods=['POST'])
def categorize_charts():
    """Fetches uncategorized charts, uses Gemini to categorize them, and updates the DB."""
    try:
        # Fetch charts that are not yet categorized
        response = supabase.table('iceberg_charts').select('id, name').is_('category', 'null').execute()
        charts_to_categorize = response.data
        
        if not charts_to_categorize:
            flash("All charts are already categorized!", "info")
            return redirect(url_for('manage_charts'))

        chart_names = [chart['name'] for chart in charts_to_categorize]
        model = genai.GenerativeModel('gemma-3-27b-it')
        prompt = (
            f"Categorize the following list of iceberg chart titles into a single, most fitting topic for each (e.g., 'Gaming', 'Media', 'History'). "
            f"The titles are: {', '.join(chart_names)}. "
            f"Your response must be a single valid JSON object where each key is a chart title and the value is its category. "
            f"For example: {{\"Chart Title 1\": \"Gaming\", \"Chart Title 2\": \"History\"}}."
        )
        
        response = model.generate_content(prompt)
        categorized_results = json.loads(clean_html_response(response.text))

        # Update Supabase for each chart
        updates = 0
        for chart in charts_to_categorize:
            if chart['name'] in categorized_results:
                category = categorized_results[chart['name']]
                supabase.table('iceberg_charts').update({'category': category}).eq('id', chart['id']).execute()
                updates += 1
        
        flash(f"Successfully categorized {updates} new chart(s)!", "success")

    except Exception as e:
        flash(f"An error occurred during categorization: {e}", "danger")
    
    return redirect(url_for('manage_charts'))


@app.route('/manage/chart/add', methods=['POST'])
def add_chart():
    chart_name = request.form.get('chart_name')
    if chart_name:
        supabase.table('iceberg_charts').insert({'name': chart_name}).execute()
    return redirect(url_for('manage_charts'))

@app.route('/manage/chart/delete/<int:chart_id>', methods=['POST'])
def delete_chart(chart_id):
    supabase.table('iceberg_charts').delete().eq('id', chart_id).execute()
    return redirect(url_for('manage_charts'))

@app.route('/manage/iceberg/<int:chart_id>')
def edit_iceberg(chart_id):
    chart_response = supabase.table('iceberg_charts').select('id, name').eq('id', chart_id).single().execute()
    if not chart_response.data:
        return "Chart not found", 404
    layers_response = supabase.table('iceberg_layers').select('*, iceberg_entries(*)').eq('chart_id', chart_id).order('layer_order').execute()
    return render_template('edit_iceberg.html', chart=chart_response.data, layers=layers_response.data)

@app.route('/manage/layer/add/<int:chart_id>', methods=['POST'])
def add_layer(chart_id):
    layer_name = request.form.get('layer_name')
    max_order_res = supabase.table('iceberg_layers').select('layer_order').eq('chart_id', chart_id).order('layer_order', desc=True).limit(1).execute()
    new_order = (max_order_res.data[0]['layer_order'] + 1) if max_order_res.data else 0
    if layer_name:
        supabase.table('iceberg_layers').insert({'chart_id': chart_id, 'layer_name': layer_name, 'layer_order': new_order}).execute()
    return redirect(url_for('edit_iceberg', chart_id=chart_id))

@app.route('/manage/layer/delete/<int:layer_id>', methods=['POST'])
def delete_layer(layer_id):
    layer_res = supabase.table('iceberg_layers').select('chart_id').eq('id', layer_id).single().execute()
    chart_id = layer_res.data['chart_id'] if layer_res.data else None
    supabase.table('iceberg_layers').delete().eq('id', layer_id).execute()
    if chart_id:
        return redirect(url_for('edit_iceberg', chart_id=chart_id))
    return redirect(url_for('manage_charts'))

@app.route('/manage/entry/add/<int:layer_id>', methods=['POST'])
def add_entry(layer_id):
    entry_text = request.form.get('entry_text')
    layer_res = supabase.table('iceberg_layers').select('chart_id').eq('id', layer_id).single().execute()
    chart_id = layer_res.data['chart_id']
    if entry_text:
        supabase.table('iceberg_entries').insert({'layer_id': layer_id, 'entry_text': entry_text, 'metadata': {}}).execute()
    return redirect(url_for('edit_iceberg', chart_id=chart_id))

@app.route('/manage/entry/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    entry_res = supabase.table('iceberg_entries').select('layer_id').eq('id', entry_id).single().execute()
    layer_id = entry_res.data['layer_id']
    layer_res = supabase.table('iceberg_layers').select('chart_id').eq('id', layer_id).single().execute()
    chart_id = layer_res.data['chart_id']
    supabase.table('iceberg_entries').delete().eq('id', entry_id).execute()
    return redirect(url_for('edit_iceberg', chart_id=chart_id))


if __name__ == '__main__':
    app.run(debug=True)
