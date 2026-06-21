# Chatwoot setup guide

After following the standard login procedure go to settings -> inboxes.

![[imgs/Screenshot 2026-06-21 at 15.35.59 1.png]]

![[Screenshot 2026-06-21 at 15.36.19 2.png]]

For each of the channels you want to use click "Add Inbox" -> "API"

![[imgs/Screenshot 2026-06-21 at 15.36.28.png]]

![[imgs/Screenshot 2026-06-21 at 16.07.22.png]]

For each channel write "Channel Name" and Webhook URL. The latter should follow the pattern: 
```
https://<your-domain>/ingest/outgoing/{channel}/{cw_account_id}/webhook
```
**Important:** Chatwoot doesn't support http as webhook address, so https is needed.

![[imgs/Screenshot 2026-06-21 at 15.36.36.png]]

After the setup is complete and you're ready to go!


