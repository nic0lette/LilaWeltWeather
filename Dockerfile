# Copyright 2023 lilawelt.de
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM debian:bookworm-slim

RUN apt update && \
    apt install -y python3 python3-pip
COPY requirements.txt /tmp/

# Break system packages because it's just an image anyway
RUN pip install --requirement /tmp/requirements.txt --break-system-packages

#COPY weather.service /etc/systemd/system/
#RUN systemctl enable weather
COPY config.toml /app/
COPY *.py /app/

WORKDIR /app
CMD [ "/usr/bin/python3", "/app/main.py", "--config=config.toml" ]
