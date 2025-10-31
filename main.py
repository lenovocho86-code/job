import logging
import logging.handlers
import os
import json

import datetime
import requests

from bs4 import BeautifulSoup
import time
from dotenv import load_dotenv

# Load environment variables from env file
load_dotenv('.env')

VISITED_LINKS_FOLDER = "visited_links"

SUMMER_INTERNSHIPS_URL = "https://github.com/SimplifyJobs/Summer2026-Internships"
SUMMER_LINKS_FILE = "summer_internships.json"

NEW_GRAD_URL = "https://github.com/SimplifyJobs/New-Grad-Positions"
NEW_GRAD_LINKS_FILE = "new_grad.json"

OFF_SEASON_INTERNSHIPS_URL = "https://github.com/SimplifyJobs/Summer2026-Internships/blob/dev/README-Off-Season.md"
OFF_SEASON_INTERNSHIPS_LINKS_FILE = "off_season_internships.json"

try:
    SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]
except KeyError:
    SLACK_WEBHOOK = "Token not available!"

try:
    NEW_GRAD_WEBHOOK = os.environ["NEW_GRAD_WEBHOOK"]
except KeyError:
    NEW_GRAD_WEBHOOK = "Token not available!"


def send_slack_message(message, webhook):
    payload = '{"text":"%s"}' % message
    response = requests.post(webhook, data=payload)
    print(response.text)

def scrape_internships(url):
    """
    Scrapes internship data from the Simplify Jobs GitHub repository.

    Args:
        url (str): The URL of the GitHub page to scrape.

    Returns:
        list: A list of dictionaries containing the scraped internship data,
              or an empty list if scraping fails.
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
        
        readme_div = soup.find('markdown-accessiblity-table')
        if not readme_div:
            print("Error: Could not find the main content area (readme div).")
            return []
            
        table = readme_div.find('table')
        if not table:
            print("Error: Could not find the internship table on the page.")
            return []

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

        return internship_data

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the request: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        
    return []

def load_visited_links(filepath):
    """Load visited links from a JSON file. Returns an empty set if file doesn't exist."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get('visited_links', []))
        except (json.JSONDecodeError, KeyError):
            return set()
    return set()

def save_visited_links(filepath, visited_links):
    """Save visited links to a JSON file."""
    directory = os.path.dirname(filepath)
    if directory:  # Only create directory if path has a directory component
        os.makedirs(directory, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'visited_links': list(visited_links)}, f, indent=2)

def extract_internships(url, links_filename, slack_webhook):
    start_time = time.time()
    links_filepath = os.path.join(VISITED_LINKS_FOLDER, links_filename)
    
    # Scrape current internships
    latest_internships = scrape_internships(url)
    
    if latest_internships:
        # Load previously visited links
        visited_links = load_visited_links(links_filepath)
        
        # Get current links from scraped data
        current_links = {job['Application Link'] for job in latest_internships}
        
        # Find new internships (links we haven't visited)
        new_links = current_links - visited_links
        
        if new_links:
            # Filter internships to only include new ones
            new_internships = [job for job in latest_internships if job['Application Link'] in new_links]
            
            print(f"Found {len(new_internships)} new internships:")
            for job in new_internships:
                print(f"  - {job['Company']}: {job['Role']}")
            
            formatted_string = format_internship_digest(new_internships)
            print(formatted_string)
            send_slack_message(formatted_string, slack_webhook)
            
            # Update visited links with new ones
            visited_links.update(new_links)
        else:
            print("No new internships found.")

        # Save updated visited links
        save_visited_links(links_filepath, visited_links)
    else:
        print("\nScraping failed. No data was processed.")

    end_time = time.time()
    print(f"\nTotal time taken: {end_time - start_time:.2f} seconds")

def remove_utm_params(url):
    """Remove UTM parameters from URL for Slack notifications."""
    utm_suffix = "?utm_source=Simplify&ref=Simplify"
    if url.endswith(utm_suffix):
        # Cut off the last 33 characters (?utm_source=Simplify&ref=Simplify)
        return url[:-33]
    return url

def format_internship_digest(internships):
    """Formats a list of new internships into a single digest message."""
    
    # Start with a title line.
    message_lines = [f"🔥 *{len(internships)} New Jobs Found!*"]

    # Loop through each internship to build the list
    for job in internships:
        company = f"*{job['Company']}*" # Bold the company name
        
        # Truncate the role text to keep the line from wrapping on mobile
        role = job['Role']
        short_role = (role[:40] + '...') if len(role) > 43 else role
        
        # Remove UTM parameters from URL for Slack
        clean_url = remove_utm_params(job['Application Link'])
        
        # Create a clean link using Slack's format: <URL|Display Text>
        link = f"<{clean_url}|{short_role}>"
        
        # Add the formatted line to our list
        message_lines.append(f"• {company} - {link}")
        
    # Join all the lines together with a newline character in between
    # Using a double newline for the title gives it some nice space.
    return message_lines[0] + "\n\n" + "\n".join(message_lines[1:])

if __name__ == "__main__":
    extract_internships(SUMMER_INTERNSHIPS_URL, SUMMER_LINKS_FILE, SLACK_WEBHOOK)
    extract_internships(NEW_GRAD_URL, NEW_GRAD_LINKS_FILE, NEW_GRAD_WEBHOOK)
    # extract_internships(OFF_SEASON_INTERNSHIPS_URL, OFF_SEASON_INTERNSHIPS_LINKS_FILE, "idk")