.PHONY: regen-chatwoot-client
regen-chatwoot-client:  ## 🚀 Generate Chatwoot API client
	@bash chatwoot_spec/regen.sh

# Or shoter:
.PHONY: regen
regen: regen-chatwoot-client  ## 🚀 Generate Chatwoot API client
