import requests

def send_slack_message(message):
    payload = '{"text":"%s"}' % message
    response = requests.post('***REMOVED-SLACK-WEBHOOK***', data=payload)
    print(response.text)

if __name__ == "__main__":
    send_slack_message(message)