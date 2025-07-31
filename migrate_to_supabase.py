import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from postgrest.exceptions import APIError

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and Key must be set in the .env file.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ICEBERG_DIR = 'icebergs'

def migrate_data():
    """
    Reads JSON files from the 'icebergs' directory and populates Supabase tables.
    """
    print("Starting migration...")

    # Get list of JSON files
    json_files = [f for f in os.listdir(ICEBERG_DIR) if f.endswith('.json')]

    for file_name in json_files:
        chart_name = os.path.splitext(file_name)[0].replace('_', ' ')
        print(f"\nProcessing chart: {chart_name}")

        try:
            # Check if chart already exists
            existing_chart_res = supabase.table('iceberg_charts').select('id').eq('name', chart_name).execute()
            if existing_chart_res.data:
                print(f"Chart '{chart_name}' already exists. Skipping.")
                continue

            # 1. Insert the chart
            chart_insert_res = supabase.table('iceberg_charts').insert({'name': chart_name}).execute()
            chart_id = chart_insert_res.data[0]['id']
            print(f"  -> Chart '{chart_name}' inserted with ID: {chart_id}")

            # Load the JSON data
            with open(os.path.join(ICEBERG_DIR, file_name), 'r', encoding='utf-8') as f:
                iceberg_data = json.load(f)

            # 2. Insert layers and entries
            for i, layer_data in enumerate(iceberg_data):
                layer_name = layer_data.get('layer')
                if not layer_name:
                    continue

                layer_insert_res = supabase.table('iceberg_layers').insert({
                    'chart_id': chart_id,
                    'layer_name': layer_name,
                    'layer_order': i
                }).execute()
                layer_id = layer_insert_res.data[0]['id']
                print(f"    -> Layer '{layer_name}' inserted with ID: {layer_id}")

                entries_to_insert = []
                for entry_data in layer_data.get('entries', []):
                    entry_text = entry_data.get('text')
                    if entry_text: # Ensure entry text is not empty
                        entries_to_insert.append({
                            'layer_id': layer_id,
                            'entry_text': entry_text,
                            'metadata': json.dumps(entry_data.get('metadata', {})) # Ensure metadata is a valid JSON string
                        })
                
                if entries_to_insert:
                    entries_insert_res = supabase.table('iceberg_entries').insert(entries_to_insert).execute()
                    print(f"      -> Inserted {len(entries_insert_res.data)} entries.")

        except APIError as e:
            print(f"  -> A Supabase API Error occurred: {e.message}")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Could not read or parse {file_name}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred with chart '{chart_name}': {e}")


    print("\nMigration complete!")

if __name__ == '__main__':
    migrate_data()
