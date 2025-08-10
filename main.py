import logging
import logging.handlers
import os

import datetime
import requests

import pandas as pd
from bs4 import BeautifulSoup
import time

URL = "https://github.com/SimplifyJobs/Summer2026-Internships"

def scrape_internships(url):
    """
    Scrapes internship data from the Simplify Jobs GitHub repository.

    Args:
        url (str): The URL of the GitHub page to scrape.

    Returns:
        pandas.DataFrame: A DataFrame containing the scraped internship data,
                          or an empty DataFrame if scraping fails.
    """
    try:
        # 1. Fetch the HTML content of the page
        print(f"Fetching data from {url}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        
        # Raise an exception if the request was unsuccessful (e.g., 404 Not Found)
        response.raise_for_status()
        print("Successfully fetched page content.")
        
        # 2. Parse the HTML with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the table in the README file's content
        # GitHub renders the README's table inside a div with id="readme"
        readme_div = soup.find('markdown-accessiblity-table')
        if not readme_div:
            print("Error: Could not find the main content area (readme div).")
            return pd.DataFrame()
            
        table = readme_div.find('table')
        if not table:
            print("Error: Could not find the internship table on the page.")
            return pd.DataFrame()

        # 3. Extract the data from the table rows
        internship_data = []
        # Find all rows in the table body (tbody)
        rows = table.find('tbody').find_all('tr')
        print(f"Found {len(rows)} internship listings. Processing...")

        for row in rows:
            cells = row.find_all('td')
            # Ensure the row has the expected number of columns
            if len(cells) == 5:
                company = cells[0].get_text(strip=True)
                role = cells[1].get_text(strip=True)
                location = cells[2].get_text(strip=True)
                application_cell = cells[3]
                date_posted = cells[4].get_text(strip=True)
                
                # Extract the link from the 'Application/Link' cell
                link_tag = application_cell.find('a')
                application_link = link_tag['href'] if link_tag else 'N/A'
                
                # Add the extracted data as a dictionary to our list
                internship_data.append({
                    'Company': company,
                    'Role': role,
                    'Location': location,
                    'Application Link': application_link,
                    'Date Posted': date_posted
                })

        # 4. Create a Pandas DataFrame
        df = pd.DataFrame(internship_data)
        return df

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the request: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        
    return pd.DataFrame()

def extract_internships():
    start_time = time.time()
    
    internship_df = scrape_internships(URL)
    
    if not internship_df.empty:
        # 5. Save the data to a CSV file
        output_filename = 'internships.csv'
        internship_df.to_csv(output_filename, index=False, encoding='utf-8')
        
        # print("\n--- Scraping Summary ---")
        # print(f"Successfully scraped {len(internship_df)} internships.")
        # print(f"Data saved to '{output_filename}'")
        
        # # Display the first 5 rows of the DataFrame
        # print("\nFirst 5 listings:")
        # print(internship_df.head())
    else:
        print("\nScraping failed. No data was saved.")

    end_time = time.time()
    print(f"\nTotal time taken: {end_time - start_time:.2f} seconds")
    return internship_df

try:
    SOME_SECRET = os.environ["SOME_SECRET"]
except KeyError:
    SOME_SECRET = "Token not available!"


if __name__ == "__main__":
    df = extract_internships()

    # --- Define formatters to truncate long text ---
    formatters = {
        'Role': lambda x: x[:30] + '...' if len(x) > 33 else x,
        'Application Link': lambda x: x[:35] + '...' if len(x) > 38 else x
    }

    # --- Convert the DataFrame to a formatted string ---
    formatted_string = df.head(10).to_string(
        formatters=formatters,
        justify='left'
    )
    # r = requests.get('https://weather.talkpython.fm/api/weather/?city=Berlin&country=DE')
    # if r.status_code == 200:
    #     data = r.json()
    #     temperature = data["forecast"]["temp"]