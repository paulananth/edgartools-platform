-- Derived word index: fixed-length native tokens retain short and stop words.
ALTER TABLE code ADD COLUMN _search_tokens LONGTEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT ('') COMMENT 'Native fixed-length word tokens; rebuilt from labels before approval and by owner upgrade'
-- statement boundary
ALTER TABLE code_label ADD COLUMN _search_tokens LONGTEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT ('') COMMENT 'Native fixed-length word tokens; rebuilt from labels before approval and by owner upgrade'
-- statement boundary
CREATE FULLTEXT INDEX code_search_tokens_words ON code (_search_tokens)
-- statement boundary
CREATE FULLTEXT INDEX code_label_search_tokens_words ON code_label (_search_tokens)
