"""Run rules every reported result must follow.

BLOCKED_DOMAINS: the agent must not search or open these sites (or their subdomains). The Global AI Regulation Tracker
is where many of the benchmark's developments were first recorded, with links to their official sources, so an agent
that reads it is looking up the answer rather than researching it. Block them in your agent's search and fetch tools.
"""
BLOCKED_DOMAINS = ('techieray.com',)


def uses_blocked_domain(url: str) -> bool:
    from techieray_training_lab.common.matching import host
    h = host(url)
    return any(h == d or h.endswith('.' + d) for d in BLOCKED_DOMAINS)
