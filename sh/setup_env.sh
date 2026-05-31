# shellcheck shell=bash

vector_db_provider="${1:-chroma}"

if [[ "$vector_db_provider" == "opensearch" ]]; then
  vector_db_host=localhost
  vector_db_port=9200
  vector_db_write_username=bob
  vector_db_write_password='X5@mD8!zH3#uC1%w'
  vector_db_read_username=alice
  vector_db_read_password='N7!qL2#vP9@tR4$k'

  vector_db_build_args="--vectorDbProvider opensearch --vectorDbHost $vector_db_host --vectorDbPort $vector_db_port --vectorDbUseSsl --vectorDbUsername $vector_db_write_username --vectorDbPassword $vector_db_write_password"
  vector_db_query_args="--vectorDbProvider opensearch --vectorDbHost $vector_db_host --vectorDbPort $vector_db_port --vectorDbUseSsl --vectorDbUsername $vector_db_read_username --vectorDbPassword $vector_db_read_password"
elif [[ "$vector_db_provider" == "chroma" ]]; then
  vector_db_host=localhost
  vector_db_port=8000
  vector_db_build_args="--vectorDbProvider chroma --vectorDbHost $vector_db_host --vectorDbPort $vector_db_port"
  vector_db_query_args="$vector_db_build_args"
else
  echo "Unsupported vector_db_provider: $vector_db_provider. Use 'chroma' or 'opensearch'."
  return 1 2>/dev/null || exit 1
fi
