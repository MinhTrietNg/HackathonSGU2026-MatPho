typedef FeedSource = ({String uri, Duration start, Duration? end});

FeedSource networkFeed(String url) =>
    (uri: url, start: Duration.zero, end: null);

extension FeedSourceKind on FeedSource {
  bool get isNetwork => uri.startsWith('https://') || uri.startsWith('http://');
}
