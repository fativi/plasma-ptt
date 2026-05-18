PREFIX ?= /usr
DESTDIR ?=

.PHONY: all install uninstall

all:
	@echo "Nothing to build. Run 'make install' to install."

install:
	# Install the executable
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 plasma-ptt.py $(DESTDIR)$(PREFIX)/bin/plasma-ptt

	# Install the desktop entry
	install -d $(DESTDIR)$(PREFIX)/share/applications
	install -m 644 plasma-ptt.desktop $(DESTDIR)$(PREFIX)/share/applications/plasma-ptt.desktop

	# Install default sounds
	install -d $(DESTDIR)$(PREFIX)/share/plasma-ptt/sounds
	install -m 644 sounds/*.wav $(DESTDIR)$(PREFIX)/share/plasma-ptt/sounds/

	# Install the systemd user service
	install -d $(DESTDIR)$(PREFIX)/lib/systemd/user
	sed 's|^ExecStart=.*|ExecStart=$(PREFIX)/bin/plasma-ptt|' plasma-ptt.service > plasma-ptt.service.tmp
	install -m 644 plasma-ptt.service.tmp $(DESTDIR)$(PREFIX)/lib/systemd/user/plasma-ptt.service
	rm -f plasma-ptt.service.tmp

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/plasma-ptt
	rm -f $(DESTDIR)$(PREFIX)/share/applications/plasma-ptt.desktop
	rm -rf $(DESTDIR)$(PREFIX)/share/plasma-ptt
	rm -f $(DESTDIR)$(PREFIX)/lib/systemd/user/plasma-ptt.service
