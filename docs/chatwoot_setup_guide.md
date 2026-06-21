After following the standard login procedure go to settings -> inboxes.

![Settings inboxes menu](imgs/Screenshot%202026-06-21%20at%2015.35.59%201.png)
![Inboxes page](imgs/Screenshot%202026-06-21%20at%2015.36.19%202.png)

For each of the channels you want to use click "Add Inbox" -> "API"

![Add inbox button](imgs/Screenshot%202026-06-21%20at%2015.36.28.png)
![API channel option](imgs/Screenshot%202026-06-21%20at%2016.07.22.png)

For each channel write "Channel Name" and Webhook URL. The latter should follow the pattern:

```
https://<your-domain>/ingest/outgoing/{channel}/{cw_account_id}/webhook
```

**Important:** Chatwoot doesn't support http as webhook address, so https is needed.

![Channel name and webhook URL fields](imgs/Screenshot%202026-06-21%20at%2015.36.36.png)

After the setup is complete and you're ready to go!
