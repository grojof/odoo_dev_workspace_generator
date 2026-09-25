# Design

## Same place as the statement lines repair

This fix also belongs right after 14.0, with the same condition (a source up to 13.0) and the same tool:
the 14.0 Odoo's shell. So it goes in the same script. One shell run carries both repairs, and the step
record gets one `repair` line per repair.

## Through the ORM

In 14.0 `l10n.es.aeat.certificate.file` is an attachment, so writing it through the ORM stores it where
Odoo reads it. In 12.0 a non-attachment binary column holds the value base64-encoded, which is the form
the ORM takes, so the value is written as read.

## What it does not do

It cannot obtain the keys: that needs the certificate's password, which is the client's, and the new
server's disk. It says so in the output. It also does not re-point the attachments the OCA script moved
to the wrong id, because the copies seen so far had none. A client whose file was an attachment in 12.0 is
not covered yet.
