FROM opensearchproject/opensearch:3.3.0

USER root

RUN /usr/share/opensearch/bin/opensearch-plugin install -b transport-reactor-netty4

USER opensearch
