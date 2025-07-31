import os
import json
import re
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

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
    return text

# --- Main Routes ---

@app.route('/')
def index():
    """Displays the list of available iceberg charts from Supabase."""
    if not supabase:
        return "Supabase client not initialized. Check your .env configuration.", 500
    
    response = supabase.table('iceberg_charts').select('name').order('name').execute()
    charts = [chart['name'] for chart in response.data] if response.data else []
    return render_template('index.html', charts=charts)

@app.route('/iceberg/<chart_name>')
def iceberg_chart(chart_name):
    """Displays a specific iceberg chart by fetching its full data from Supabase."""
    if not supabase:
        return "Supabase client not initialized.", 500

    # 1. Get chart ID
    chart_response = supabase.table('iceberg_charts').select('id').eq('name', chart_name).single().execute()
    if not chart_response.data:
        return "Chart not found", 404
    chart_id = chart_response.data['id']

    # 2. Get all layers and their entries for that chart
    layers_response = supabase.table('iceberg_layers').select('*, iceberg_entries(*)').eq('chart_id', chart_id).order('layer_order').execute()
    if not layers_response.data:
        # Handle case where chart exists but has no layers
        return render_template('iceberg.html', chart_name=chart_name, iceberg_data=[], total_entries=0)

    # 3. Format data for the template
    iceberg_data = []
    total_entries = 0
    for layer in layers_response.data:
        entries = layer.get('iceberg_entries', [])
        iceberg_data.append({
            'layer': layer['layer_name'],
            'entries': [{'text': entry['entry_text']} for entry in entries]
        })
        total_entries += len(entries)

    return render_template('iceberg.html', chart_name=chart_name, iceberg_data=iceberg_data, total_entries=total_entries)

# --- Explanation API ---

@app.route('/api/explain', methods=['POST'])
def get_explanation():
    """API endpoint to get an explanation and related image for an iceberg entry."""
    data = request.json
    chart_name = data.get('chart_name')
    entry_text = data.get('entry_text')

    if not all([chart_name, entry_text, GEMINI_API_KEY, CUSTOM_SEARCH_API_KEY, CUSTOM_SEARCH_ENGINE_ID]):
        return jsonify({'error': 'Missing data or API key configuration.'}), 400

    # --- UPDATED SEARCH LOGIC ---
    # 1. Get text context from Google Custom Search with multiple query attempts
    search_context = "Web search failed or returned no results."
    queries_to_try = [
        f'"{entry_text}" meaning in "{chart_name}" iceberg chart',
        f'"{entry_text}" iceberg explanation',
        f'"{entry_text}" lore'
    ]
    
    for query in queries_to_try:
        try:
            print(f"Attempting search with query: {query}")
            text_search_params = {'key': CUSTOM_SEARCH_API_KEY, 'cx': CUSTOM_SEARCH_ENGINE_ID, 'q': query, 'num': 3}
            response = requests.get(CUSTOM_SEARCH_URL, params=text_search_params)
            response.raise_for_status()
            search_json = response.json()
            snippets = [item.get('snippet', '') for item in search_json.get('items', [])]
            if snippets:
                search_context = " ".join(snippets)
                print(f"  -> Success! Found context for '{entry_text}'.")
                break # Stop searching if we find results
            else:
                print(f"  -> Query returned no results.")
        except requests.exceptions.RequestException as e:
            print(f"  -> Search failed for query '{query}': {e}")
            continue # Try the next query

    # 2. Get a related image with a simple query
    image_url = None
    try:
        image_search_query = f'"{entry_text}"'
        image_search_params = {'key': CUSTOM_SEARCH_API_KEY, 'cx': CUSTOM_SEARCH_ENGINE_ID, 'q': image_search_query, 'searchType': 'image', 'num': 1}
        response = requests.get(CUSTOM_SEARCH_URL, params=image_search_params)
        response.raise_for_status()
        image_results = response.json().get('items', [])
        if image_results:
            image_url = image_results[0].get('link')
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch image results: {e}")

    # 3. Generate explanation with Gemini
    prompt = (
        f"You are an expert explainer of internet culture. Provide a clear, concise explanation for the iceberg entry: '{entry_text}' "
        f"from the '{chart_name}' iceberg chart. Use this web search context: '{search_context}'. "
        f"Format your response in simple HTML using paragraphs (<p>) and bold tags (<b>)."
    )
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        explanation = clean_html_response(response.text)
        return jsonify({'explanation': explanation, 'image_url': image_url})
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return jsonify({'error': f'Failed to process AI explanation: {e}'}), 500


# --- CRUD Management Routes (unchanged) ---

@app.route('/manage')
def manage_charts():
    """Page to manage all iceberg charts."""
    response = supabase.table('iceberg_charts').select('id, name').order('name').execute()
    charts = response.data if response.data else []
    return render_template('manage_charts.html', charts=charts)

@app.route('/manage/chart/add', methods=['POST'])
def add_chart():
    """Adds a new chart."""
    chart_name = request.form.get('chart_name')
    if chart_name:
        supabase.table('iceberg_charts').insert({'name': chart_name}).execute()
    return redirect(url_for('manage_charts'))

@app.route('/manage/chart/delete/<int:chart_id>', methods=['POST'])
def delete_chart(chart_id):
    """Deletes a chart and all its related layers and entries (cascade)."""
    supabase.table('iceberg_charts').delete().eq('id', chart_id).execute()
    return redirect(url_for('manage_charts'))

@app.route('/manage/iceberg/<int:chart_id>')
def edit_iceberg(chart_id):
    """Page to edit a specific iceberg's layers and entries."""
    chart_response = supabase.table('iceberg_charts').select('id, name').eq('id', chart_id).single().execute()
    if not chart_response.data:
        return "Chart not found", 404
    
    layers_response = supabase.table('iceberg_layers').select('*, iceberg_entries(*)').eq('chart_id', chart_id).order('layer_order').execute()
    
    return render_template('edit_iceberg.html', chart=chart_response.data, layers=layers_response.data)

@app.route('/manage/layer/add/<int:chart_id>', methods=['POST'])
def add_layer(chart_id):
    """Adds a new layer to a chart."""
    layer_name = request.form.get('layer_name')
    max_order_res = supabase.table('iceberg_layers').select('layer_order').eq('chart_id', chart_id).order('layer_order', desc=True).limit(1).execute()
    new_order = (max_order_res.data[0]['layer_order'] + 1) if max_order_res.data else 0
    
    if layer_name:
        supabase.table('iceberg_layers').insert({'chart_id': chart_id, 'layer_name': layer_name, 'layer_order': new_order}).execute()
    return redirect(url_for('edit_iceberg', chart_id=chart_id))

@app.route('/manage/layer/delete/<int:layer_id>', methods=['POST'])
def delete_layer(layer_id):
    """Deletes a layer."""
    layer_res = supabase.table('iceberg_layers').select('chart_id').eq('id', layer_id).single().execute()
    chart_id = layer_res.data['chart_id'] if layer_res.data else None
    
    supabase.table('iceberg_layers').delete().eq('id', layer_id).execute()
    
    if chart_id:
        return redirect(url_for('edit_iceberg', chart_id=chart_id))
    return redirect(url_for('manage_charts'))

@app.route('/manage/entry/add/<int:layer_id>', methods=['POST'])
def add_entry(layer_id):
    """Adds a new entry to a layer."""
    entry_text = request.form.get('entry_text')
    layer_res = supabase.table('iceberg_layers').select('chart_id').eq('id', layer_id).single().execute()
    chart_id = layer_res.data['chart_id']
    
    if entry_text:
        supabase.table('iceberg_entries').insert({'layer_id': layer_id, 'entry_text': entry_text, 'metadata': {}}).execute()
    
    return redirect(url_for('edit_iceberg', chart_id=chart_id))

@app.route('/manage/entry/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    """Deletes an entry."""
    entry_res = supabase.table('iceberg_entries').select('layer_id').eq('id', entry_id).single().execute()
    layer_id = entry_res.data['layer_id']
    layer_res = supabase.table('iceberg_layers').select('chart_id').eq('id', layer_id).single().execute()
    chart_id = layer_res.data['chart_id']

    supabase.table('iceberg_entries').delete().eq('id', entry_id).execute()
    
    return redirect(url_for('edit_iceberg', chart_id=chart_id))


if __name__ == '__main__':
    app.run(debug=True)
