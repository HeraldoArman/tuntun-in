# GoWA — go-whatsapp-web-multidevice REST API.
# Used by the Reflex agent to send Overwatch (emergency spectator) WhatsApp
# alerts to a blind user's linked guardian.
#
# We deploy the upstream image as-is; the entrypoint is the `whatsapp` binary,
# so CMD just passes the `rest` subcommand + port. EXPOSE 3000 so Railway
# routes health checks + traffic to the right port.
FROM aldinokemal2104/go-whatsapp-web-multidevice:latest

EXPOSE 3000

CMD ["rest", "--port=3000"]