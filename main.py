import logging
import logging.handlers
import os

import datetime
import requests

import pandas as pd
from bs4 import BeautifulSoup
import time

URL = "https://github.com/SimplifyJobs/Summer2026-Internships"
try:
    SLACK_WEBHOOK = os.environ["SOME_SECRET"]
except KeyError:
    SLACK_WEBHOOK = "Token not available!"
print(SLACK_WEBHOOK)

def send_slack_message(message):
    payload = '{"text":"%s"}' % message
    response = requests.post(SLACK_WEBHOOK, data=payload)
    print(response.text)

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
    
    latest_internship_df = scrape_internships(URL)
    
    if not latest_internship_df.empty:
        new_internships_df = pd.DataFrame()
        output_filename = 'internships.csv'
        if os.path.exists(output_filename):
            old_df = pd.read_csv(output_filename)
            if old_df.iloc[0]['Application Link'] != latest_internship_df.iloc[0]['Application Link']:
                merged_df = pd.merge(
                    latest_internship_df,
                    old_df,
                    on=['Application Link'], # Use the unique link to compare rows
                    how='left',
                    indicator=True
                )
                new_internships_df = merged_df[merged_df['_merge']== 'left_only'].drop(columns=['_merge'])
        else:
            new_internships_df = latest_internship_df

        if not new_internships_df.empty:
            print(new_internships_df)
            formatted_string = format_internship_digest(new_internships_df)
            send_slack_message(formatted_string)
        else:
            print("nothing")

        # 5. Save the data to a CSV file
        latest_internship_df.to_csv(output_filename, index=False, encoding='utf-8')
    else:
        print("\nScraping failed. No data was saved.")

    end_time = time.time()
    print(f"\nTotal time taken: {end_time - start_time:.2f} seconds")

def format_internship_digest(df):
    """Formats a DataFrame of new internships into a single digest message."""
    
    # Start with a title line.
    message_lines = [f"🔥 *{len(df)} New Internships Found!*"]

    # Loop through each row in the DataFrame to build the list
    for index, row in df.iterrows():
        company = f"*{row['Company_x']}*" # Bold the company name
        
        # Truncate the role text to keep the line from wrapping on mobile
        role = row['Role_x']
        short_role = (role[:40] + '...') if len(role) > 43 else role
        
        # Create a clean link using Slack's format: <URL|Display Text>
        link = f"<{row['Application Link']}|{short_role}>"
        
        # Add the formatted line to our list
        message_lines.append(f"• {company} - {link}")
        
    # Join all the lines together with a newline character in between
    # Using a double newline for the title gives it some nice space.
    return message_lines[0] + "\n\n" + "\n".join(message_lines[1:])

if __name__ == "__main__":
    extract_internships()