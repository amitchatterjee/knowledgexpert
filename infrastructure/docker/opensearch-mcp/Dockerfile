ARG OPENSEARCH_VERSION=latest
FROM opensearchproject/opensearch:${OPENSEARCH_VERSION}

USER root

RUN /usr/share/opensearch/bin/opensearch-plugin list | grep -q '^transport-reactor-netty4$' || \
	/usr/share/opensearch/bin/opensearch-plugin install -b transport-reactor-netty4

USER opensearch
